# -*- coding: utf-8 -*-
"""
utils.py
通用工具集合：
- 本地数据读写与索引
- URL 规范化与去重
- HTTP GET（重试/退避）
- RSS/HTML 元数据提取
- Sitemap 解析（含无 lastmod 的日期启发式）
- HTML 规范化：图片/链接绝对化、懒加载、安全清理（保留媒体）
"""

import os
import json
import re
import time
import hashlib
import gzip
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, urljoin
from dateutil import parser as dtparser
import requests
from bs4 import BeautifulSoup

# 数据目录与文件
DATA_ROOT = os.path.join("docs", "data")
INDEX_FILE = os.path.join(DATA_ROOT, "index.json")
DEDUP_FILE = os.path.join(DATA_ROOT, "dedup.json")

# HTTP 请求默认头
HEADERS = {
    "User-Agent": "NewsPortalBot/1.6 (+https://github.com/) requests",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/rss+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}

# 认为可重试的状态码
RETRY_STATUS = {429, 500, 502, 503, 504}

# 跟踪参数（从 URL query 中剔除）
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "mbid", "partner", "ncid", "cmpid", "icid", "ref", "refsrc", "oref", "_hsmi", "_hsenc",
    "fbclid", "gclid", "smid", "emc", "share", "s_cid", "sref", "rss", "output", "mod",
    "algo", "variant"
}

# 基础文件/目录操作
def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, obj):
    ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# 通用
def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return re.sub(r"^www\.", "", netloc)
    except Exception:
        return ""

def canonicalize_url(u: str) -> str:
    """统一 URL：https、去 www/m/amp、去掉末尾斜杠、清理追踪参数与 amp 标记"""
    try:
        parts = urlparse(u.strip())
        scheme = "https"
        netloc = re.sub(r"^(m|amp|www)\.", "", parts.netloc.lower())
        path = re.sub(r"/+$", "", parts.path)
        path = re.sub(r"/amp/?$", "", path).replace("/amp/", "/")
        q = [
            (k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS and v.lower() != "amp"
        ]
        query = urlencode(q, doseq=True)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return u

def to_iso(dt) -> str:
    """转 ISO8601，统一为 UTC"""
    if isinstance(dt, str):
        dt = dtparser.parse(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

# 本地数据分月文件
def monthly_file(year: int, month: int) -> str:
    return os.path.join(DATA_ROOT, f"{year:04d}", f"{month:02d}.json")

def load_month(year: int, month: int):
    path = monthly_file(year, month)
    if not os.path.exists(path):
        return []
    return load_json(path, [])

def save_month(year: int, month: int, items):
    path = monthly_file(year, month)
    items_sorted = sorted(items, key=lambda x: x.get("published_at", ""), reverse=True)
    save_json(path, items_sorted)

def load_dedup():
    return set(load_json(DEDUP_FILE, []))

def save_dedup(s):
    save_json(DEDUP_FILE, sorted(list(s)))

def update_index_indexfile():
    """重建月份索引 + 生成时间"""
    months = {}
    ensure_dir(DATA_ROOT)
    for y in sorted(os.listdir(DATA_ROOT)):
        ydir = os.path.join(DATA_ROOT, y)
        if not os.path.isdir(ydir):
            continue
        for m in sorted(os.listdir(ydir)):
            if not m.endswith(".json"):
                continue
            path = os.path.join(ydir, m)
            try:
                data = load_json(path, [])
                months[f"{y}-{m[:-5]}"] = len(data)
            except Exception:
                pass
    index = {
        "months": sorted(months.keys()),
        "counts": months,
        "generated_at": to_iso(datetime.now(timezone.utc)),
    }
    save_json(INDEX_FILE, index)

def add_item_if_new(dedup_set, item):
    """写入新条目并更新去重集"""
    if item["id"] in dedup_set:
        return False
    dt = dtparser.parse(item["published_at"])
    y, m = dt.year, dt.month
    arr = load_month(y, m)
    arr.append(item)
    save_month(y, m, arr)
    dedup_set.add(item["id"])
    return True

def make_item(url, title, source, published_at_iso, summary=None, author=None, updated_at=None):
    url_c = canonicalize_url(url)
    return {
        "id": sha1(url_c),
        "url": url_c,
        "title": title or "(No title)",
        "source": source,
        "published_at": published_at_iso,
        "updated_at": updated_at or "",
        "author": author or "",
        "summary": summary or "",
        "lang": "en",
        "content_text": "",
        "content_html": "",
        "cover_image": "",
        "can_publish_fulltext": False,
    }

# 网络请求
def http_get(url, headers=None, timeout=25, max_retries=3, backoff=1.6):
    """带重试与指数退避的 GET；支持 Retry-After"""
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    last_exc = None
    delay = 1.0
    for attempt in range(max_retries + 1):
        try:
            r = requests.get(url, headers=h, timeout=timeout)
            if r.status_code in RETRY_STATUS:
                ra = r.headers.get("Retry-After")
                if ra:
                    try:
                        delay = max(delay, float(ra))
                    except Exception:
                        pass
                last_exc = Exception(f"HTTP {r.status_code}")
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= backoff
                    continue
                r.raise_for_status()
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(delay)
                delay *= backoff
                continue
            raise last_exc

def parse_xml(content_bytes: bytes) -> str:
    """自动解压 .gz 并返回 UTF-8 文本"""
    data = content_bytes
    if content_bytes[:2] == b"\x1f\x8b":
        data = gzip.decompress(content_bytes)
    return data.decode("utf-8", "ignore")

# HTML 元数据提取
def _first_meta(soup, names=None, props=None):
    if names:
        for n in names:
            el = soup.find("meta", attrs={"name": n})
            if el and el.get("content"):
                return el["content"].strip()
    if props:
        for p in props:
            el = soup.find("meta", attrs={"property": p})
            if el and el.get("content"):
                return el["content"].strip()
    return None

def _from_ld_json(soup):
    import json
    authors, published, modified = [], None, None
    for tag in soup.find_all("script", attrs={"type": lambda v: v and "ld+json" in v}):
        txt = tag.string or tag.get_text()
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for obj in items:
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type") or ""
            if isinstance(t, list):
                t = ",".join(t)
            if any(x in str(t) for x in ["NewsArticle", "Article", "Report", "BlogPosting"]):
                ap = obj.get("author")
                if isinstance(ap, dict):
                    n = ap.get("name")
                    n and authors.append(n)
                elif isinstance(ap, list):
                    for a in ap:
                        if isinstance(a, dict):
                            n = a.get("name")
                            n and authors.append(n)
                if not published:
                    published = obj.get("datePublished")
                if not modified:
                    modified = obj.get("dateModified")
                if authors or published or modified:
                    return (authors, published, modified)
    return (authors, published, modified)

def extract_meta_from_html(html_text: str):
    soup = BeautifulSoup(html_text, "html.parser")
    # 标题
    title = _first_meta(soup, props=["og:title", "twitter:title"]) or (
        soup.title.string.strip() if soup.title and soup.title.string else None
    )
    # 作者
    author = _first_meta(soup, names=["author", "byl", "byline"], props=["article:author"])
    ld_authors, ld_pub, ld_mod = _from_ld_json(soup)
    if not author and ld_authors:
        author = ", ".join(dict.fromkeys([a.strip() for a in ld_authors if a and isinstance(a, str)]))
    if author:
        author = re.sub(r"^\s*by\s+", "", author, flags=re.I).strip()

    # 时间
    published = (
        _first_meta(soup, props=["article:published_time"])
        or _first_meta(soup, names=["pubdate", "publishdate", "date", "ptime", "DC.date.issued"])
        or ld_pub
    )
    modified = _first_meta(soup, props=["article:modified_time"]) or ld_mod

    return {
        "title": title or "",
        "author": author or "",
        "published_at": to_iso(published) if published else "",
        "updated_at": to_iso(modified) if modified else "",
    }

def extract_meta(url: str, timeout=18):
    try:
        r = http_get(
            url,
            headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
            timeout=timeout,
        )
        if "text/html" not in r.headers.get("Content-Type", "").lower():
            return {}
        return extract_meta_from_html(r.text)
    except Exception:
        return {}

# HTML 规范化：保留媒体、绝对化 img/src/href、懒加载
def transform_content_html(html_text: str, base_url: str) -> str:
    """
    - 保留图片/figure/figcaption
    - 去 script/style/iframe/noscript
    - 统一 a[href] 与 img[src] 为绝对 URL
    - 兼容 data-src/data-original/srcset，尽量补齐 img.src
    - 图片懒加载（loading=lazy + decoding=async），链接加安全属性
    """
    soup = BeautifulSoup(html_text or "", "html.parser")
    # 清理危险标签
    for t in soup(["script", "style", "noscript", "iframe"]):
        t.decompose()

    # 修正图片
    for img in soup.find_all("img"):
        for k in ["data-src", "data-original", "data-lazy-src", "data-ks-lazyload", "data-image"]:
            if not img.get("src") and img.get(k):
                img["src"] = img.get(k)
        if not img.get("src") and img.get("srcset"):
            try:
                candidates = [c.strip() for c in img["srcset"].split(",")]
                img["src"] = candidates[-1].split()[0]
            except Exception:
                pass
        if img.get("src"):
            img["src"] = urljoin(base_url, img["src"])
        img["loading"] = img.get("loading") or "lazy"
        img["decoding"] = img.get("decoding") or "async"
        img.attrs.pop("onload", None)
        img.attrs.pop("onclick", None)

    # 修正 <source srcset>
    for src in soup.find_all("source"):
        if src.get("srcset"):
            parts = []
            for seg in src["srcset"].split(","):
                p = seg.strip().split()
                if not p:
                    continue
                absu = urljoin(base_url, p[0])
                parts.append(absu if len(p) == 1 else f"{absu} {p[1]}")
            if parts:
                src["srcset"] = ", ".join(parts)

    # 链接绝对化与安全属性
    for a in soup.find_all("a"):
        href = a.get("href")
        if href:
            a["href"] = urljoin(base_url, href)
            a["target"] = "_blank"
            a["rel"] = "noopener noreferrer"
        for attr in list(a.attrs.keys()):
            if attr.lower().startswith("on"):
                a.attrs.pop(attr, None)

    return str(soup)

# Sitemap 解析（含无 lastmod 的路径日期启发式）
def collect_from_sitemap_index(base_url, start_iso, end_iso, polite_delay=0.6, include_no_lastmod=True):
    """
    解析 sitemap 或 sitemap 索引。
    - 先按 <sitemap><lastmod> 对子索引做粗过滤，减少无关抓取
    - <url> 无 <lastmod> 时，用“路径日期启发式”（/2025/09/... 或 2025-09-12）估算时间
    返回: [(url, iso_lastmod), ...]
    """
    from xml.etree import ElementTree as ET

    start = dtparser.parse(start_iso)
    end = dtparser.parse(end_iso)

    try:
        idx_resp = http_get(base_url, timeout=40)
    except Exception as e:
        print(f"Fetch sitemap index failed: {base_url} - {e}")
        return []

    xml = parse_xml(idx_resp.content)
    try:
        root = ET.fromstring(xml)
    except Exception as e:
        print(f"Parse sitemap index failed: {base_url} - {e}")
        return []

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap_nodes = root.findall(".//sm:sitemap", ns)
    children = []

    if sitemap_nodes:
        for sm in sitemap_nodes:
            loc_el = sm.find("sm:loc", ns)
            lm_el = sm.find("sm:lastmod", ns)
            if loc_el is None or not loc_el.text:
                continue
            loc = loc_el.text.strip()

            # 子索引粗过滤：±40 天缓冲
            if lm_el is not None and lm_el.text:
                try:
                    lm = dtparser.parse(lm_el.text.strip())
                    if lm < (start - timedelta(days=40)) or lm > (end + timedelta(days=40)):
                        continue
                except Exception:
                    pass
            children.append(loc)
    else:
        children = [base_url]

    results, seen = [], set()
    # 匹配 /2025/09/ 或 /2025-09(-dd)/
    date_pat = re.compile(r"/(20\d{2})(?:[-/])(\d{1,2})(?:[-/](\d{1,2}))?")

    for child in children:
        time.sleep(polite_delay)
        try:
            r = http_get(child, timeout=50)
        except Exception as e:
            print(f"Fetch sitemap child failed: {child} - {e}")
            continue

        try:
            # 用 XML 解析器也可，BeautifulSoup 更宽容
            croot = BeautifulSoup(parse_xml(r.content), "xml")
        except Exception as e:
            print(f"Parse child sitemap failed: {child} - {e}")
            continue

        for u in croot.find_all("url"):
            loc_el = u.find("loc")
            lm_el = u.find("lastmod")
            if loc_el is None or not loc_el.text:
                continue
            loc = loc_el.text.strip()
            if loc in seen:
                continue
            seen.add(loc)

            used_dt = None

            # 优先使用 <lastmod>
            if lm_el is not None and lm_el.text:
                try:
                    dtv = dtparser.parse(lm_el.text.strip())
                    if start <= dtv <= end:
                        used_dt = dtv
                except Exception:
                    pass

            # 无 lastmod 或 lastmod 不在区间，用路径日期启发式
            if used_dt is None and include_no_lastmod:
                m = date_pat.search(loc)
                if m:
                    y, mon, d = int(m.group(1)), int(m.group(2)), m.group(3)
                    day = int(d) if d and d.isdigit() else 15  # 无日取月中
                    try:
                        approx = datetime(y, mon, day, tzinfo=timezone.utc)
                        if start <= approx <= end:
                            used_dt = approx
                    except Exception:
                        pass

            if used_dt is None:
                continue

            results.append((loc, to_iso(used_dt)))

    return results
