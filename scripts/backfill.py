# -*- coding: utf-8 -*-
import os, sys, time, json
from datetime import datetime, timezone
from dateutil import parser as dtparser

from scripts.config import SOURCES, START_DATE_ISO
from scripts.utils import (
    collect_from_sitemap_index, extract_meta, load_dedup, save_dedup,
    add_item_if_new, make_item, to_iso, update_index_indexfile,
    ensure_dir
)
from scripts.connectors.fulltext import extract_fulltext

STATE_FILE = os.path.join("docs", "data", "backfill_state.json")

# 默认参数
DEFAULT_MAX_MONTHS_PER_RUN = 2
DEFAULT_MAX_URLS_PER_SOURCE_PER_MONTH = 150
DEFAULT_BACKFILL_DELAY = 0.18

def getenv_int(name, default):
    v = os.getenv(name)
    if v is None: return default
    v = str(v).strip()
    if not v: return default
    try: return int(v)
    except: return default

def getenv_float(name, default):
    v = os.getenv(name)
    if v is None: return default
    v = str(v).strip()
    if not v: return default
    try: return float(v)
    except: return default

# 环境参数（健壮解析）
MAX_MONTHS_PER_RUN = getenv_int("MAX_MONTHS_PER_RUN", DEFAULT_MAX_MONTHS_PER_RUN)
MAX_URLS_PER_SOURCE_PER_MONTH = getenv_int("MAX_URLS_PER_SOURCE_PER_MONTH", DEFAULT_MAX_URLS_PER_SOURCE_PER_MONTH)
POLITE_DELAY = getenv_float("BACKFILL_DELAY", DEFAULT_BACKFILL_DELAY)

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

def month_list(start_dt, end_dt):
    y, m = start_dt.year, start_dt.month
    while True:
        cur = datetime(y, m, 1, tzinfo=timezone.utc)
        if cur > end_dt: break
        yield (y, m)
        m += 1
        if m > 12: m = 1; y += 1

def load_state():
    if not os.path.exists(STATE_FILE): return None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def save_state(state):
    ensure_dir(os.path.dirname(STATE_FILE))
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)

def main():
    # 先读旧状态
    old_state = load_state()

    # 解析时间区间（输入为空则优先沿用旧区间，保证不被“now”打断）
    start_raw = (os.getenv("BACKFILL_START") or "").strip()
    end_raw   = (os.getenv("BACKFILL_END") or "").strip()
    start_iso = start_raw or (old_state.get("start_iso") if old_state else "") or (START_DATE_ISO + "T00:00:00Z")
    end_iso   = end_raw   or (old_state.get("end_iso")   if old_state else "") or to_iso(datetime.now(timezone.utc))

    start_dt = dtparser.parse(start_iso)
    end_dt   = dtparser.parse(end_iso)

    # 初始或沿用进度
    state = old_state or {
        "start_iso": start_iso,
        "end_iso": end_iso,
        "source_idx": 0,
        "month_idx": 0,
        "complete": False
    }

    # 如果手动输入了新的时间区间，与旧值不同则重置进度
    if (start_raw and start_iso != state.get("start_iso")) or (end_raw and end_iso != state.get("end_iso")):
        state = {
            "start_iso": start_iso,
            "end_iso": end_iso,
            "source_idx": 0,
            "month_idx": 0,
            "complete": False
        }

    if state.get("complete"):
        print("Backfill already complete for the given range.")
        return 0

    sources_keys = list(SOURCES.keys())
    months = list(month_list(start_dt, end_dt))
    if not months:
        print("No months to backfill in given range.")
        return 0

    source_idx = int(state.get("source_idx", 0))
    month_idx  = int(state.get("month_idx", 0))

    dedup = load_dedup()
    added_total = 0
    months_processed_this_run = 0

    while source_idx < len(sources_keys) and months_processed_this_run < MAX_MONTHS_PER_RUN:
        skey = sources_keys[source_idx]
        conf = SOURCES[skey]
        sitemap = conf.get("sitemap")
        if not sitemap:
            source_idx += 1
            month_idx = 0
            continue

        if month_idx >= len(months):
            source_idx += 1
            month_idx = 0
            continue

        y, m = months[month_idx]
        month_start = datetime(y, m, 1, tzinfo=timezone.utc)
        if m == 12:
            month_end = datetime(y+1, 1, 1, tzinfo=timezone.utc)
        else:
            month_end = datetime(y, m+1, 1, tzinfo=timezone.utc)
        month_start_iso = to_iso(month_start)
        month_end_iso   = to_iso(month_end)

        print(f"[{conf['display_name']}] Backfill {y}-{m:02d} via sitemap: {sitemap}")
        rows = collect_from_sitemap_index(
            sitemap, month_start_iso, month_end_iso,
            polite_delay=0.5, include_no_lastmod=True
        ) or []
        print(f"  URLs in month: {len(rows)} (limit {MAX_URLS_PER_SOURCE_PER_MONTH})")
        processed = 0

        for (url, lastmod_iso) in rows[:MAX_URLS_PER_SOURCE_PER_MONTH]:
            meta = extract_meta(url)
            title = meta.get("title","") or conf["display_name"]
            author = meta.get("author","")
            published = meta.get("published_at") or lastmod_iso
            updated = meta.get("updated_at","")
            item = make_item(url, title, conf["display_name"], published, None, author, updated)
            item = try_fill_fulltext(item)
            if add_item_if_new(dedup, item):
                added_total += 1
            processed += 1
            time.sleep(POLITE_DELAY)

        month_idx += 1
        months_processed_this_run += 1
        state.update({
            "start_iso": start_iso,
            "end_iso": end_iso,   # 固定本次区间，不随“now”漂移
            "source_idx": source_idx,
            "month_idx": month_idx,
            "complete": False
        })
        save_state(state)

        print(f"  Done {y}-{m:02d}: processed={processed}, added_total={added_total}")

        if month_idx >= len(months):
            source_idx += 1
            month_idx = 0

    if source_idx >= len(sources_keys):
        state.update({"complete": True})
        save_state(state)
        print("Backfill fully complete for the given range.")

    save_dedup(dedup)
    update_index_indexfile()
    print(f"Backfill chunk done. New items added this run: {added_total}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
