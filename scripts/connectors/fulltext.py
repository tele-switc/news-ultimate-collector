# -*- coding: utf-8 -*-
"""
全文抽取（本地解析，不绕过付费墙）：
- trafilatura: 结构化元数据 + 纯文本
- readability: 清洁 HTML（保留图片）
- transform_content_html: 绝对化图片/链接、懒加载、安全清理
- 若正文无图，尝试用 og:image 作为封面图插入
"""
import json
from readability import Document
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from datetime import datetime, timezone
from scripts.utils import http_get, transform_content_html, extract_og_image_src

def _to_iso(dt):
    if not dt: return ""
    if isinstance(dt, str):
        try: d = dtparser.parse(dt)
        except Exception: return ""
    else:
        d = dt
    if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat()

def extract_fulltext(url: str, timeout: int = 60):
    r = http_get(url, headers={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}, timeout=timeout)
    if "text/html" not in r.headers.get("Content-Type","").lower():
        return {}

    page_html = r.text

    # 1) trafilatura（纯文本 + 元数据）
    meta_title = meta_author = meta_date = ""
    text_plain = ""
    try:
        import trafilatura
        j = trafilatura.extract(page_html, output_format="json", favor_recall=True, include_comments=False, url=url)
        if j:
            data = json.loads(j)
            text_plain  = (data.get("text") or "").strip()
            meta_title  = (data.get("title") or "").strip()
            meta_author = (data.get("author") or "").strip()
            meta_date   = _to_iso(data.get("date"))
    except Exception:
        pass

    # 2) readability（清洁 HTML）
    content_html = ""
    try:
        doc = Document(page_html)
        content_html = doc.summary() or ""
        if not meta_title:
            meta_title = (doc.short_title() or "").strip()
    except Exception:
        pass

    # 3) HTML 规范化
    if content_html:
        content_html = transform_content_html(content_html, url)
        # 若正文没有任何图片，注入 og:image 作为封面图
        try:
            soup = BeautifulSoup(content_html, "html.parser")
            if not soup.find("img"):
                og = extract_og_image_src(page_html, url)
                if og:
                    hero = soup.new_tag("figure", **{"class":"hero"})
                    img = soup.new_tag("img", src=og, loading="lazy")
                    hero.append(img)
                    soup.insert(0, hero)
                    content_html = str(soup)
        except Exception:
            pass

    # 4) 如果没拿到纯文本，基于 HTML 兜底
    if not text_plain and content_html:
        try:
            text_plain = BeautifulSoup(content_html, "html.parser").get_text("\n").strip()
        except Exception:
            pass

    return {
        "title": meta_title or "",
        "author": meta_author or "",
        "published_at": meta_date or "",
        "updated_at": "",
        "content_text": text_plain or "",
        "content_html": content_html or "",
    }
