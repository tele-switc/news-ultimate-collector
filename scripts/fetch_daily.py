# -*- coding: utf-8 -*-
import sys, time, os, subprocess
from datetime import datetime, timezone, timedelta
import feedparser
from dateutil import parser as dtparser

from scripts.config import SOURCES, START_DATE_ISO, SITEMAP_LOOKBACK_HOURS
from scripts.utils import (
    HEADERS, load_dedup, save_dedup, add_item_if_new, make_item, to_iso,
    update_index_indexfile, extract_meta, collect_from_sitemap_index
)
from scripts.connectors.fulltext import extract_fulltext

DEFAULT_COMMIT_EVERY = 120
DEFAULT_TIME_BUDGET_MIN = 30
DEFAULT_TIME_HEADROOM_SEC = 70

def getenv_int(name, default):
    v = os.getenv(name)
    if v is None: return default
    v = str(v).strip()
    if not v: return default
    try: return int(v)
    except: return default

COMMIT_EVERY = getenv_int("COMMIT_EVERY_DAILY", DEFAULT_COMMIT_EVERY)
TIME_BUDGET_MIN = getenv_int("TIME_BUDGET_MIN_DAILY", DEFAULT_TIME_BUDGET_MIN)
TIME_HEADROOM_SEC = getenv_int("TIME_HEADROOM_SEC_DAILY", DEFAULT_TIME_HEADROOM_SEC)

def git_checkpoint_commit(message="chore(daily): checkpoint"):
    try:
        if os.getenv("GITHUB_ACTIONS", "").lower() != "true":
            return
        # 配置用户（若上游步骤未配置）
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        # 仅添加数据
        subprocess.run(["git", "add", "docs/data"], check=True)
        # 有变更才提交
        if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
            return
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
        subprocess.run(["git", "commit", "-m", f"{message} @ {ts}"], check=True)
        # push 前先拉取rebase，避免非快进
        branch = os.getenv("GITHUB_REF_NAME", "main")
        subprocess.run(["git", "pull", "--rebase", "origin", branch], check=False)
        subprocess.run(["git", "push", "origin", branch], check=True)
        print("Daily checkpoint committed and pushed.")
    except Exception as e:
        print(f"Daily checkpoint commit skipped: {e}")

def checkpoint(dedup, note="daily-checkpoint"):
    save_dedup(dedup)
    update_index_indexfile()
    git_checkpoint_commit(note)

def time_is_up(start_ts: float) -> bool:
    elapsed = time.monotonic() - start_ts
    budget = max(120, TIME_BUDGET_MIN * 60)
    return elapsed >= max(60, budget - TIME_HEADROOM_SEC)

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
    return ""

def try_fill_fulltext(item):
    try:
        data = extract_fulltext(item["url"])
        if not data: return item
        if data.get("title"):        item["title"] = item["title"] or data["title"]
        if data.get("author"):       item["author"] = item["author"] or data["author"]
        if data.get("published_at"): item["published_at"] = data["published_at"]
        if data.get("updated_at"):   item["updated_at"] = data["updated_at"]
        if data.get("cover_image"):  item["cover_image"] = data["cover_image"]
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
    start_ts = time.monotonic()

    dedup = load_dedup()
    total_added = 0
    processed_since_commit = 0

    for key, conf in SOURCES.items():
        if time_is_up(start_ts):
            checkpoint(dedup, "daily-time-budget")
            print("Daily time budget reached. Exit with saved progress.")
            return 0

        src_added = 0
        for rss in conf.get("rss", []):
            print(f"[{conf['display_name']}] RSS: {rss}")
            feed = feedparser.parse(rss, request_headers=HEADERS)
            for e in getattr(feed, "entries", []):
                if time_is_up(start_ts):
                    checkpoint(dedup, "daily-time-budget")
                    print("Daily time budget reached mid-RSS. Exit with saved progress.")
                    return 0

                url = e.get("link") or e.get("id")
                if not url: continue
                published_iso = entry_time(e)
                if not published_iso:
                    meta = extract_meta(url)
                    if meta.get("published_at"): published_iso = meta["published_at"]
                if not published_iso or published_iso < start_iso:
                    continue

                title = (e.get("title") or "").strip()
                summary = (e.get("summary") or e.get("description") or "").strip()
                author = (e.get("author") or "").strip()
                updated_at = ""

                if not author or not title:
                    meta = extract_meta(url)
                    if meta.get("author") and not author: author = meta["author"]
                    if meta.get("title") and not title:   title  = meta["title"]
                    if meta.get("published_at"):          published_iso = meta["published_at"]
                    if meta.get("updated_at"):            updated_at    = meta["updated_at"]
                    time.sleep(0.12)

                item = make_item(url, title or conf["display_name"], conf["display_name"], published_iso, summary, author, updated_at)
                item = try_fill_fulltext(item)

                if add_item_if_new(dedup, item):
                    src_added += 1
                    total_added += 1
                    processed_since_commit += 1

                if processed_since_commit >= COMMIT_EVERY:
                    checkpoint(dedup, "daily-autosave")
                    processed_since_commit = 0

            time.sleep(0.2)

        if src_added == 0 and conf.get("sitemap"):
            start_fallback_iso = to_iso(now - timedelta(hours=SITEMAP_LOOKBACK_HOURS))
            end_iso = to_iso(now)
            print(f"[{conf['display_name']}] Sitemap 兜底 {start_fallback_iso} ~ {end_iso}")
            rows = collect_from_sitemap_index(conf["sitemap"], start_fallback_iso, end_iso, polite_delay=0.35) or []
            for (url, lastmod_iso) in rows:
                if time_is_up(start_ts):
                    checkpoint(dedup, "daily-time-budget")
                    print("Daily time budget reached mid-Sitemap. Exit with saved progress.")
                    return 0
                if lastmod_iso < start_iso:
                    continue

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
                    processed_since_commit += 1

                if processed_since_commit >= COMMIT_EVERY:
                    checkpoint(dedup, "daily-autosave")
                    processed_since_commit = 0
                time.sleep(0.1)

    checkpoint(dedup, "daily-final")
    print(f"Done. New items added: {total_added}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
