# -*- coding: utf-8 -*-
"""
全文抽取（本地解析，不绕过付费墙）：
- trafilatura: 结构化元数据 + 纯文本
- readability: 清洁 HTML（保留图片）
- transform_content_html: 绝对化图片/链接、懒加载、安全清理
- 提取封面图：og:image 或正文第一张图
"""
import json
from readability import Document
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from datetime import datetime, timezone
from scripts.utils import http_get, transform_content_html

def _to_iso(dt):
    if not dt: return ""
    if isinstance(dt, str):
        try: d = dtparser.parse(dt)
        except Exception: return ""
    else:
        d = dt
    if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat()

def _cover_from_html(raw_html: str, base_url: str) -> str:
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        og = soup.find("meta", attrs={"property":"og:image"})
        if og and og.get("content"):
            return og["content"].strip()
        # 退化到正文第一张
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"].strip()
    except Exception:
        pass
    return ""

def _cover_from_content(content_html: str, base_url: str) -> str:
    try:
        soup = BeautifulSoup(content_html or "", "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"].strip()
    except Exception:
        pass
    return ""

def extract_fulltext(url: str, timeout: int = 60):
    r = http_get(url, headers={
        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }, timeout=timeout)
    ctype = r.headers.get("Content-Type","").lower()
    if "text/html" not in ctype:
        return {}

    raw_html = r.text

    # 1) trafilatura（元数据 + 纯文本）
    meta_title = meta_author = meta_date = ""
    text_plain = ""
    try:
        import trafilatura
        j = trafilatura.extract(raw_html, output_format="json", favor_recall=True, include_comments=False, url=url)
        if j:
            data = json.loads(j)
            text_plain  = (data.get("text") or "").strip()
            meta_title  = (data.get("title") or "").strip()
            meta_author = (data.get("author") or "").strip()
            meta_date   = _to_iso(data.get("date"))
    except Exception:
        pass

    # 2) readability（清洁 HTML，包含图片）
    content_html = ""
    try:
        doc = Document(raw_html)
        content_html = doc.summary() or ""
        if not meta_title:
            meta_title = (doc.short_title() or "").strip()
    except Exception:
        pass

    # 3) HTML 规范化：绝对化图片/链接、懒加载、安全清理（保留媒体）
    cover = _cover_from_html(raw_html, url)
    if content_html:
        content_html = transform_content_html(content_html, url)
        if not cover:
            cover = _cover_from_content(content_html, url)

    # 若没拿到纯文本，基于 HTML 辅助生成
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
        "cover_image": cover or "",
    }
