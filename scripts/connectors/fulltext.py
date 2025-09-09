# -*- coding: utf-8 -*-
import json
from readability import Document
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from datetime import datetime, timezone
from scripts.utils import http_get

def _to_iso(dt):
    if not dt: return ""
    if isinstance(dt, str):
        try: d = dtparser.parse(dt)
        except Exception: return ""
    else:
        d = dt
    if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat()

def extract_fulltext(url: str, timeout: int = 45):
    """
    本地解析（trafilatura + readability），仅在页面本身可访问时提取正文。
    不绕过付费墙/登录；不可访问则返回空。
    """
    r = http_get(url, headers={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}, timeout=timeout)
    if "text/html" not in r.headers.get("Content-Type","").lower():
        return {}

    html = r.text

    # 1) trafilatura（元数据 + 纯文本）
    meta_title = meta_author = meta_date = ""
    text_plain = ""
    try:
        import trafilatura
        j = trafilatura.extract(html, output_format="json", favor_recall=True, include_comments=False, url=url)
        if j:
            data = json.loads(j)
            text_plain = (data.get("text") or "").strip()
            meta_title = (data.get("title") or "").strip()
            meta_author = (data.get("author") or "").strip()
            meta_date = _to_iso(data.get("date"))
    except Exception:
        pass

    # 2) readability（清洁 HTML）
    content_html = ""
    try:
        doc = Document(html)
        content_html = doc.summary()
        if not meta_title:
            meta_title = (doc.short_title() or "").strip()
    except Exception:
        pass

    # 3) 清理 HTML（去 script/style/iframe）
    if content_html:
        try:
            soup = BeautifulSoup(content_html, "html.parser")
            for t in soup(["script","style","noscript","iframe"]): t.decompose()
            content_html = str(soup)
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
