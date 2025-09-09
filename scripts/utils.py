# -*- coding: utf-8 -*-
import os, json, re, time, hashlib, gzip
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from dateutil import parser as dtparser
import requests
from bs4 import BeautifulSoup

DATA_ROOT = os.path.join("docs", "data")
INDEX_FILE = os.path.join(DATA_ROOT, "index.json")
DEDUP_FILE = os.path.join(DATA_ROOT, "dedup.json")

HEADERS = {
    "User-Agent": "NewsPortalBot/1.4 (+https://github.com/) requests",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/rss+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}
RETRY_STATUS = {429, 500, 502, 503, 504}
TRACKING_PARAMS = {
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content","utm_id",
    "mbid","partner","ncid","cmpid","icid","ref","refsrc","oref","_hsmi","_hsenc",
    "fbclid","gclid","smid","emc","share","s_cid","sref","rss","output","mod","algo","variant"
}

def ensure_dir(p): os.makedirs(p, exist_ok=True)
def load_json(path, default):
    if not os.path.exists(path): return default
    with open(path, "r", encoding="utf-8") as f: return json.load(f)
def save_json(path, obj):
    ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def sha1(s: str) -> str: return hashlib.sha1(s.encode("utf-8")).hexdigest()
def domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return re.sub(r"^www\.", "", netloc)
    except Exception:
        return ""

def canonicalize_url(u: str) -> str:
    try:
        parts = urlparse(u.strip())
        scheme = "https"
        netloc = re.sub(r"^(m|amp|www)\.", "", parts.netloc.lower())
        path = re.sub(r"/+$", "", parts.path)
        path = re.sub(r"/amp/?$", "", path).replace("/amp/", "/")
        q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS and v.lower() != "amp"]
        query = urlencode(q, doseq=True)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return u

def to_iso(dt) -> str:
    if isinstance(dt, str): dt = dtparser.parse(dt)
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def monthly_file(year: int, month: int) -> str:
    return os.path.join(DATA_ROOT, f"{year:04d}", f"{month:02d}.json")
def load_month(year: int, month: int):
    path = monthly_file(year, month)
    if not os.path.exists(path): return []
    return load_json(path, [])
def save_month(year: int, month: int, items):
    path = monthly_file(year, month)
    items_sorted = sorted(items, key=lambda x: x.get("published_at",""), reverse=True)
    save_json(path, items_sorted)

def load_dedup(): return set(load_json(DEDUP_FILE, []))
def save_dedup(s): save_json(DEDUP_FILE, sorted(list(s)))

def update_index_indexfile():
    months = {}
    ensure_dir(DATA_ROOT)
    for y in sorted(os.listdir(DATA_ROOT)):
        ydir = os.path.join(DATA_ROOT, y)
        if not os.path.isdir(ydir): continue
        for m in sorted(os.listdir(ydir)):
            if not m.endswith(".json"): continue
            path = os.path.join(ydir, m)
            try:
                data = load_json(path, [])
                months[f"{y}-{m[:-5]}"] = len(data)
            except Exception: pass
    index = {"months": sorted(months.keys()), "counts": months, "generated_at": to_iso(datetime.now(timezone.utc))}
    save_json(INDEX_FILE, index)

def add_item_if_new(dedup_set, item):
    if item["id"] in dedup_set: return False
    dt = dtparser.parse(item["published_at"])
    y, m = dt.year, dt.month
    arr = load_month(y, m); arr.append(item); save_month(y, m, arr)
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
        "can_publish_fulltext": False,
    }

def http_get(url, headers=None, timeout=25, max_retries=3, backoff=1.6):
    h = dict(HEADERS)
    if headers: h.update(headers)
    last_exc = None
    delay = 1.0
    for attempt in range(max_retries + 1):
        try:
            r = requests.get(url, headers=h, timeout=timeout)
            if r.status_code in RETRY_STATUS:
                ra = r.headers.get("Retry-After")
                if ra:
                    try: delay = max(delay, float(ra))
                    except Exception: pass
                last_exc = Exception(f"HTTP {r.status_code}")
                if attempt < max_retries:
                    time.sleep(delay); delay *= backoff; continue
                r.raise_for_status()
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(delay); delay *= backoff; continue
            raise last_exc

def parse_xml(content_bytes):
    data = content_bytes
    if content_bytes[:2] == b"\x1f\x8b":
        data = gzip.decompress(content_bytes)
    return data.decode("utf-8", "ignore")

def _first_meta(soup, names=None, props=None):
    if names:
        for n in names:
            el = soup.find("meta", attrs={"name": n})
            if el and el.get("content"): return el["content"].strip()
    if props:
        for p in props:
            el = soup.find("meta", attrs={"property": p})
            if el and el.get("content"): return el["content"].strip()
    return None

def _from_ld_json(soup):
    import json
    authors, published, modified = [], None, None
    for tag in soup.find_all("script", attrs={"type": lambda v: v and "ld+json" in v}):
        txt = tag.string or tag.get_text()
        if not txt: continue
        try:
            data = json.loads(txt)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for obj in items:
            if not isinstance(obj, dict): continue
            t = obj.get("@type") or ""
            if isinstance(t, list): t = ",".join(t)
            if any(x in str(t) for x in ["NewsArticle","Article","Report","BlogPosting"]):
                ap = obj.get("author")
                if isinstance(ap, dict):
                    n = ap.get("name");  n and authors.append(n)
                elif isinstance(ap, list):
                    for a in ap:
                        if isinstance(a, dict):
                            n = a.get("name"); n and authors.append(n)
                if not published: published = obj.get("datePublished")
                if not modified: modified = obj.get("dateModified")
                if authors or published or modified:
                    return (authors, published, modified)
    return (authors, published, modified)

def extract_meta_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    title = _first_meta(soup, props=["og:title","twitter:title"]) or (soup.title.string.strip() if soup.title and soup.title.string else None)
    author = _first_meta(soup, names=["author","byl","byline"], props=["article:author"])
    ld_authors, ld_pub, ld_mod = _from_ld_json(soup)
    if not author and ld_authors:
        author = ", ".join(dict.fromkeys([a.strip() for a in ld_authors if a and isinstance(a, str)]))
    if author:
        author = re.sub(r"^\s*by\s+", "", author, flags=re.I).strip()
    published = _first_meta(soup, props=["article:published_time"]) or _first_meta(soup, names=["pubdate","publishdate","date","ptime","DC.date.issued"]) or ld_pub
    modified  = _first_meta(soup, props=["article:modified_time"]) or ld_mod
    return {
        "title": title or "",
        "author": author or "",
        "published_at": to_iso(published) if published else "",
        "updated_at": to_iso(modified) if modified else "",
    }

def extract_meta(url, timeout=18):
    try:
        r = http_get(url, headers={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}, timeout=timeout)
        if "text/html" not in r.headers.get("Content-Type","").lower(): return {}
        return extract_meta_from_html(r.text)
    except Exception:
        return {}

# 读取站点 Sitemap（返回 (url, lastmod_iso)）
def collect_from_sitemap_index(base_url, start_iso, end_iso, polite_delay=0.6):
    from xml.etree import ElementTree as ET
    start = dtparser.parse(start_iso); end = dtparser.parse(end_iso)
    try:
        idx = http_get(base_url, timeout=40)
    except Exception as e:
        print(f"Fetch sitemap index failed: {base_url} - {e}")
        return []
    xml = parse_xml(idx.content)
    try:
        root = ET.fromstring(xml)
    except Exception as e:
        print(f"Parse sitemap index failed: {base_url} - {e}")
        return []
    ns = {"sm":"http://www.sitemaps.org/schemas/sitemap/0.9"}
    nodes = root.findall(".//sm:sitemap", ns)
    children = [base_url] if not nodes else [n.find("sm:loc", ns).text.strip() for n in nodes if n.find("sm:loc", ns) is not None]
    seen, results = set(), []
    for child in children:
        time.sleep(polite_delay)
        try:
            r = http_get(child, timeout=50)
        except Exception as e:
            print(f"Fetch sitemap child failed: {child} - {e}"); continue
        try:
            croot = ET.fromstring(parse_xml(r.content))
        except Exception as e:
            print(f"Parse child sitemap failed: {child} - {e}"); continue
        for uel in croot.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}url"):
            loc_el = uel.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            lm_el  = uel.find("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod")
            if not loc_el or not loc_el.text: continue
            loc = loc_el.text.strip()
            if loc in seen: continue
            seen.add(loc)
            if not lm_el or not lm_el.text: continue
            try:
                lastmod_iso = to_iso(lm_el.text.strip())
            except Exception:
                continue
            dt = dtparser.parse(lastmod_iso)
            if start <= dt <= end:
                results.append((loc, lastmod_iso))
    return results
