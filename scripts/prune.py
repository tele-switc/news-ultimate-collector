# -*- coding: utf-8 -*-
import os, json
from scripts.utils import DATA_ROOT, DEDUP_FILE, INDEX_FILE, load_json, save_json, update_index_indexfile

def monthly_files():
    for y in sorted(os.listdir(DATA_ROOT)):
        ydir = os.path.join(DATA_ROOT, y)
        if not os.path.isdir(ydir): continue
        for m in sorted(os.listdir(ydir)):
            if not m.endswith(".json"): continue
            yield os.path.join(ydir, m)

def keep_item(it):
    # 保留条件：
    # 1) 来自 GitHub 导入（source 以 "GitHub: " 开头），或
    # 2) 有站内可读全文（content_html 或 content_text 非空）
    src = (it.get("source") or "")
    if src.startswith("GitHub: "):
        return True
    if (it.get("content_html") or "").strip():
        return True
    if (it.get("content_text") or "").strip():
        return True
    return False

def main():
    print("[prune] start")
    total_before = 0
    total_after = 0
    ids = []

    for path in monthly_files():
        arr = load_json(path, [])
        total_before += len(arr)
        kept = [it for it in arr if keep_item(it)]
        total_after += len(kept)
        save_json(path, kept)
        ids.extend([it["id"] for it in kept])

    # 重建去重文件
    save_json(DEDUP_FILE, sorted(list(set(ids))))
    # 重建 index
    update_index_indexfile()

    print(f"[prune] before={total_before} after={total_after} removed={total_before-total_after}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
