# -*- coding: utf-8 -*-
import os, sys, time
from datetime import datetime, timezone
from scripts.config import SOURCES, START_DATE_ISO
from scripts.utils import (
    collect_from_sitemap_index, extract_meta, load_dedup, save_dedup,
    add_item_if_new, make_item, to_iso, update_index_indexfile
)
from scripts.connectors.fulltext import extract_fulltext

def try_fill_fulltext(item):
    try:
        data = extract_fulltext(item["url"])
        if not data: return item
        if data.get("title"): item["title"] = item["title"] or data["title"]
        if data.get("author"): item["author"] = item["author"] or data["author"]
        if data.get("published_at"): item["published_at"] = data["published_at"]
        if data.get("updated_at"): item["updated_at"] = data["updated_at"]
        item["content_text"] = data.get("content_text") or ""
        item["content_html"] = data.get("content_html") or ""
        if item["content_text"] or item["content_html"]:
            item["can_publish_fulltext"] = True
    except Exception as e:
        print(f"Fulltext extract failed: {e}")
    return item

def main():
    start_iso = os.getenv("BACKFILL_START", START_DATE_ISO + "T00:00:00Z")
    end_iso = os.getenv("BACKFILL_END", to_iso(datetime.now(timezone.utc)))
    dedup = load_dedup()

    added = 0
    for key, conf in SOURCES.items():
        base = conf.get("sitemap")
        if not base: continue
        print(f"[{conf['display_name']}] Sitemap backfill: {base}")
        rows = collect_from_sitemap_index(base, start_iso, end_iso, polite_delay=0.6)
        print(f"  URLs in range: {len(rows)}")
        for (url, lastmod_iso) in rows:
            meta = extract_meta(url)
            title = meta.get("title","") or conf["display_name"]
            author = meta.get("author","")
            published = meta.get("published_at") or lastmod_iso
            updated = meta.get("updated_at","")
            item = make_item(url, title, conf["display_name"], published, None, author, updated)
            item = try_fill_fulltext(item)
            if add_item_if_new(dedup, item): added += 1
            time.sleep(0.18)

    save_dedup(dedup)
    update_index_indexfile()
    print(f"Backfill done. New items added: {added}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
