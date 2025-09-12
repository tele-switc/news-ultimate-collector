# -*- coding: utf-8 -*-
import sys, time
from datetime import datetime, timezone, timedelta
import feedparser
from dateutil import parser as dtparser
from scripts.config import SOURCES, START_DATE_ISO, SITEMAP_LOOKBACK_HOURS, GITHUB_REPOS
from scripts.utils import (HEADERS, load_dedup, save_dedup, add_item_if_new, make_item, to_iso, update_index_indexfile, extract_meta, collect_from_sitemap_index)
from scripts.connectors.fulltext import extract_fulltext
from scripts.connectors.github_repos import collect_repo_items

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
    return to_iso(datetime.now(timezone.utc))

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

def import_github_repos(dedup):
    added = 0
    for cfg in GITHUB_REPOS:
        owner, repo = cfg["owner"], cfg["repo"]
        print(f"[GitHub] Import {owner}/{repo} ...")
        try:
            items = collect_repo_items(owner=owner, repo=repo, branch=cfg.get("branch",""), roots=cfg.get("roots") or ["."], exts=cfg.get("exts") or [".md",".txt",".html"], max_files=int(cfg.get("max_files", 100)))
            for it in items:
                base = make_item(it["url"], it["title"], it.get("source_label") or f"GitHub: {owner}/{repo}", it["published_at"], summary="")
                base["author"] = it.get("author","")
                base["content_text"] = it.get("content_text","")
                base["content_html"] = it.get("content_html","")
                base["can_publish_fulltext"] = bool(it.get("can_publish_fulltext"))
                if add_item_if_new(dedup, base): added += 1
        except Exception as e:
            print(f"GitHub import failed for {owner}/{repo}: {e}")
    return added

def main():
    start_iso = START_DATE_ISO + "T00:00:00Z"
    now = datetime.now(timezone.utc)
    dedup = load_dedup()
    total_added = 0

    for key, conf in SOURCES.items():
        src_added = 0
        for rss in conf.get("rss", []):
            print(f"[{conf['display_name']}] RSS: {rss}")
            feed = feedparser.parse(rss, request_headers=HEADERS)
            for e in getattr(feed, "entries", []):
                url = e.get("link") or e.get("id")
                if not url: continue
                published_iso = entry_time(e)
                if published_iso < start_iso: continue
                title = (e.get("title") or "").strip()
                summary = (e.get("summary") or e.get("description") or "").strip()
                author = (e.get("author") or "").strip()
                updated_at = ""
                if not author or not title:
                    meta = extract_meta(url)
                    if meta.get("author") and not author: author = meta["author"]
                    if meta.get("title") and not title: title = meta["title"]
                    if meta.get("published_at"): published_iso = meta["published_at"]
                    if meta.get("updated_at"): updated_at = meta["updated_at"]
                    time.sleep(0.2)
                item = make_item(url, title or conf["display_name"], conf["display_name"], published_iso, summary, author, updated_at)
                item = try_fill_fulltext(item)
                if add_item_if_new(dedup, item):
                    src_added += 1; total_added += 1
            time.sleep(0.3)
        if src_added == 0 and conf.get("sitemap"):
            start_fallback_iso = to_iso(now - timedelta(hours=SITEMAP_LOOKBACK_HOURS))
            end_iso = to_iso(now)
            print(f"[{conf['display_name']}] Sitemap 兜底 {start_fallback_iso} ~ {end_iso}")
            rows = collect_from_sitemap_index(conf["sitemap"], start_fallback_iso, end_iso, polite_delay=0.5)
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
                    src_added += 1; total_added += 1
                time.sleep(0.15)

    gh_added = import_github_repos(dedup)
    print(f"[GitHub] imported: {gh_added}")
    save_dedup(dedup)
    update_index_indexfile()
    print(f"Done. New items added: {total_added + gh_added}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
