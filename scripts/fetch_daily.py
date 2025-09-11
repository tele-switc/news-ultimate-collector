# -*- coding: utf-8 -*-
import sys, time
from datetime import datetime, timezone, timedelta
import feedparser
from dateutil import parser as dtparser

from scripts.config import SOURCES, START_DATE_ISO, SITEMAP_LOOKBACK_HOURS
from scripts.utils import (
    HEADERS, load_dedup, save_dedup, add_item_if_new, make_item, to_iso,
    update_index_indexfile, extract_meta, collect_from_sitemap_index
)
from scripts.connectors.fulltext import extract_fulltext

def entry_time(e):
    for k in ("published","updated","created"):
        if k in e:
            try: return to_iso(e[k])
            except Exception: pass
    for k in ("published_parsed","updated_parsed"):
        if getattr(e,k,None):
            dt = getattr(e,k)
            try: return to_iso(datetime(*dt[:6], tzinfo=timezone.utc))
            except Exception: pass
    return ""  # 不用 now，避免误排序

def try_fill_fulltext(item):
    try:
        data = extract_fulltext(item["url"])
        if not data: return item
        if data.get("title"): item["title"] = item["title"] or data["title"]
        if data.get("author"): item["author"] = item["author"] or data["author"]
        if data.get("published_at"): item["published_at"] = data["published_at"]
        if data.get("updated_at"): item["updated_at"] = data["updated_at"]
        if data.get("cover_image"): item["cover_image"] = data["cover_image"]
        item["content_text"] = data.get("content_text") or ""
        item["content_html"] = data.get("content_html") or ""
        if item["content_text"] or item["content_html"]:
            item["can_publish_fulltext"] = True
    except Exception as e:
        print(f"Fulltext extract failed: {e}")
    return item

def main():
    start_iso = START_DATE_ISO + "T00:00:00Z"
    now = datetime.now(timezone.utc)
    dedup = load_dedup()
    total_added = 0

    # 1) RSS 增量（以文章发布时间为准）
    for key, conf in SOURCES.items():
        src_added = 0
        for rss in conf.get("rss", []):
            print(f"[{conf['display_name']}] RSS: {rss}")
            feed = feedparser.parse(rss, request_headers=HEADERS)
            for e in getattr(feed, "entries", []):
                url = e.get("link") or e.get("id")
                if not url: continue
                published_iso = entry_time(e)
                # 若 feed 中没时间，尝试网页元数据补齐
                if not published_iso:
                    meta = extract_meta(url)
                    if meta.get("published_at"): published_iso = meta["published_at"]
                if not published_iso or published_iso < start_iso: 
                    continue

                title = (e.get("title") or "").strip()
                summary = (e.get("summary") or e.get("description") or "").strip()
                author = (e.get("author") or "").strip()
                updated_at = ""

                # 补齐缺失的标题/作者/时间
                if not author or not title:
                    meta = extract_meta(url)
                    if meta.get("author") and not author: author = meta["author"]
                    if meta.get("title") and not title: title = meta["title"]
                    if meta.get("published_at"): published_iso = meta["published_at"]
                    if meta.get("updated_at"): updated_at = meta["updated_at"]
                    time.sleep(0.15)

                item = make_item(url, title or conf["display_name"], conf["display_name"], published_iso, summary, author, updated_at)
                item = try_fill_fulltext(item)

                if add_item_if_new(dedup, item):
                    src_added += 1
                    total_added += 1
            time.sleep(0.25)

        # 2) RSS 无新增 → Sitemap 兜底
        if src_added == 0 and conf.get("sitemap"):
            start_fallback_iso = to_iso(now - timedelta(hours=SITEMAP_LOOKBACK_HOURS))
            end_iso = to_iso(now)
            print(f"[{conf['display_name']}] Sitemap 兜底 {start_fallback_iso} ~ {end_iso}")
            rows = collect_from_sitemap_index(conf["sitemap"], start_fallback_iso, end_iso, polite_delay=0.4)
            for (url, lastmod_iso) in rows:
                if lastmod_iso < start_iso: continue
                meta = extract_meta(url)
                title = meta.get("title","") or conf["display_name"]
                author = meta.get("author","")
                published = meta.get("published_at") or lastmod_iso
                updated = meta.get("updated_at","")
                item = make_item(url, title, conf["display_name"], published, None, author, updated)
                item = try_fill_fulltext(item)
                if add_item_if_new(dedup, item):
                    src_added += 1
                    total_added += 1
                time.sleep(0.12)

    save_dedup(dedup)
    update_index_indexfile()
    print(f"Done. New items added: {total_added}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
