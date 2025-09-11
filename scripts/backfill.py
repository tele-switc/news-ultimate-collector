# -*- coding: utf-8 -*-
import os, sys, time, json, subprocess
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
DEFAULT_MAX_MONTHS_PER_RUN = 2              # 每次分片处理月数
DEFAULT_MAX_URLS_PER_SOURCE_PER_MONTH = 150 # 每来源每月处理 URL 上限
DEFAULT_BACKFILL_DELAY = 0.15               # 每条礼貌延时（秒）
DEFAULT_COMMIT_EVERY = 120                  # 每抓到多少条做一次 checkpoint 提交
DEFAULT_TIME_BUDGET_MIN = 40                # 软时间预算（分钟），要小于 workflow timeout
DEFAULT_TIME_HEADROOM_SEC = 70              # 预留缓冲秒数（避免硬超时）

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
COMMIT_EVERY = getenv_int("COMMIT_EVERY", DEFAULT_COMMIT_EVERY)
TIME_BUDGET_MIN = getenv_int("TIME_BUDGET_MIN", DEFAULT_TIME_BUDGET_MIN)
TIME_HEADROOM_SEC = getenv_int("TIME_HEADROOM_SEC", DEFAULT_TIME_HEADROOM_SEC)

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

def git_checkpoint_commit(message="chore(backfill): checkpoint"):
    """
    在 GitHub Actions 中，从脚本内部直接 git commit + push，确保超时前已提交。
    """
    try:
        # 仅在 Actions 环境尝试
        if os.getenv("GITHUB_ACTIONS", "").lower() != "true":
            return
        # 配置
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        # 仅添加数据与状态
        subprocess.run(["git", "add", "docs/data"], check=True)
        # 有变更才提交
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return  # 无变更
        # 提交
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
        subprocess.run(["git", "commit", "-m", f"{message} @ {ts}"], check=True)
        # 推送
        branch = os.getenv("GITHUB_REF_NAME", "main")
        subprocess.run(["git", "push", "origin", branch], check=True)
        print("Checkpoint committed and pushed.")
    except Exception as e:
        print(f"Checkpoint commit skipped: {e}")

def checkpoint(dedup, state, note="checkpoint"):
    # 保存去重索引、状态、索引文件，然后 git 提交
    save_dedup(dedup)
    save_state(state)
    update_index_indexfile()
    git_checkpoint_commit(f"chore(backfill): {note}")

def time_is_up(start_ts):
    elapsed = time.monotonic() - start_ts
    budget = TIME_BUDGET_MIN * 60
    return elapsed >= max(60, budget - TIME_HEADROOM_SEC)

def main():
    # 读取旧状态，以便沿用区间
    old_state = load_state()

    # 解析区间（输入为空：优先沿用旧区间；否则用默认）
    start_raw = (os.getenv("BACKFILL_START") or "").strip()
    end_raw   = (os.getenv("BACKFILL_END") or "").strip()
    start_iso = start_raw or (old_state.get("start_iso") if old_state else "") or (START_DATE_ISO + "T00:00:00Z")
    end_iso   = end_raw   or (old_state.get("end_iso")   if old_state else "") or to_iso(datetime.now(timezone.utc))

    start_dt = dtparser.parse(start_iso)
    end_dt   = dtparser.parse(end_iso)

    # 初始化/沿用进度
    state = old_state or {
        "start_iso": start_iso,
        "end_iso": end_iso,
        "source_idx": 0,
        "month_idx": 0,
        "complete": False
    }

    # 若手动修改了区间，则重置指针
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

    start_ts = time.monotonic()
    processed_since_commit = 0

    while source_idx < len(sources_keys) and months_processed_this_run < MAX_MONTHS_PER_RUN:
        # 时间将到：先做最终 checkpoint 并优雅退出
        if time_is_up(start_ts):
            checkpoint(dedup, state, note="time-budget")
            print("Time budget reached. Gracefully exiting with saved progress.")
            return 0

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
            polite_delay=0.4, include_no_lastmod=True
        ) or []
        print(f"  URLs in month: {len(rows)} (limit {MAX_URLS_PER_SOURCE_PER_MONTH})")
        processed_this_month = 0

        for (url, lastmod_iso) in rows[:MAX_URLS_PER_SOURCE_PER_MONTH]:
            # 时间将到：checkpoint 并退出（保证已抓到的可见）
            if time_is_up(start_ts):
                state.update({
                    "start_iso": start_iso,
                    "end_iso": end_iso,
                    "source_idx": source_idx,
                    "month_idx": month_idx,
                    "complete": False
                })
                checkpoint(dedup, state, note="time-budget")
                print("Time budget reached mid-month. Progress saved.")
                return 0

            meta = extract_meta(url)
            title = meta.get("title","") or conf["display_name"]
            author = meta.get("author","")
            published = meta.get("published_at") or lastmod_iso
            updated = meta.get("updated_at","")
            item = make_item(url, title, conf["display_name"], published, None, author, updated)
            item = try_fill_fulltext(item)
            if add_item_if_new(dedup, item):
                added_total += 1
                processed_since_commit += 1
            processed_this_month += 1
            time.sleep(POLITE_DELAY)

            # 周期性 checkpoint（避免中途成果丢失）
            if processed_since_commit >= COMMIT_EVERY:
                state.update({
                    "start_iso": start_iso,
                    "end_iso": end_iso,
                    "source_idx": source_idx,
                    "month_idx": month_idx,
                    "complete": False
                })
                checkpoint(dedup, state, note="autosave")
                processed_since_commit = 0

        # 本月结束：推进指针 + checkpoint
        month_idx += 1
        months_processed_this_run += 1
        state.update({
            "start_iso": start_iso,
            "end_iso": end_iso,
            "source_idx": source_idx,
            "month_idx": month_idx,
            "complete": False
        })
        checkpoint(dedup, state, note=f"month-{y}-{m:02d}")
        print(f"  Done {y}-{m:02d}: processed={processed_this_month}, added_total={added_total}")

        if month_idx >= len(months):
            source_idx += 1
            month_idx = 0

    # 所有来源都完成
    if source_idx >= len(sources_keys):
        state.update({"complete": True})
        checkpoint(dedup, state, note="complete")
        print("Backfill fully complete for the given range.")
        return 0

    # 本次分片结束
    checkpoint(dedup, state, note="chunk-end")
    print(f"Backfill chunk done. New items added this run: {added_total}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
