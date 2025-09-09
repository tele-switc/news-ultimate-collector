# -*- coding: utf-8 -*-
import requests, re, html
from datetime import datetime, timezone
from urllib.parse import quote

HEADERS = {
    "User-Agent": "NewsPortalBot/1.4 (+https://github.com/)",
    "Accept": "application/vnd.github+json",
}

ALLOWED_LICENSES = {
    "MIT","Apache-2.0","BSD-2-Clause","BSD-3-Clause",
    "CC0-1.0","CC-BY-4.0","CC-BY-SA-4.0",
    "Unlicense","ISC","MPL-2.0"
}

def gh_get(url, timeout=30):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()

def repo_license_ok(owner, repo):
    try:
        meta = gh_get(f"https://api.github.com/repos/{owner}/{repo}")
        spdx = (meta.get("license") or {}).get("spdx_id") or "NOASSERTION"
        default_branch = meta.get("default_branch") or "main"
        return (spdx in ALLOWED_LICENSES), spdx, default_branch
    except Exception:
        return False, "UNKNOWN", "main"

def list_tree(owner, repo, branch):
    j = gh_get(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{quote(branch)}?recursive=1")
    return [n for n in j.get("tree", []) if n.get("type") == "blob"]

def fetch_raw(owner, repo, branch, path):
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    r = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"], "Accept":"text/plain"}, timeout=45)
    r.raise_for_status()
    return r.text

def md_title(text, fallback):
    for line in text.splitlines():
        t = line.strip()
        if not t: continue
        if t.startswith("#"):
            t = re.sub(r"^#+\\s*", "", t).strip()
            return t or fallback
        return t
    return fallback

def collect_repo_items(owner, repo, branch="", roots=None, exts=None, max_files=100):
    """
    仅在允许再分发的许可证下抓取全文；否则仅返回元数据（链接/标题/时间）。
    """
    roots = roots or ["."]
    exts = exts or [".md",".txt",".html"]

    ok, spdx, default_branch = repo_license_ok(owner, repo)
    branch = branch or default_branch
    tree = list_tree(owner, repo, branch)

    picked = []
    for n in tree:
        p = n.get("path") or ""
        if not any(p == r or p.startswith(r.rstrip("/") + "/") for r in roots):
            continue
        if not any(p.lower().endswith(e) for e in exts):
            continue
        picked.append(p)
        if len(picked) >= max_files: break

    items = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for path in picked:
        url = f"https://github.com/{owner}/{repo}/blob/{branch}/{path}"
        title = path.rsplit("/", 1)[-1]
        author = f"GitHub · {owner}/{repo} ({spdx})"
        content_text = ""
        content_html = ""
        can_full = False

        if ok:
            try:
                raw = fetch_raw(owner, repo, branch, path)
                content_text = raw.strip()
                if path.lower().endswith(".md"):
                    content_html = "<pre>" + html.escape(raw) + "</pre>"
                    title = md_title(raw, title)
                elif path.lower().endswith(".html"):
                    content_html = raw
                else:
                    content_html = "<pre>" + html.escape(raw) + "</pre>"
                can_full = bool(content_text or content_html)
            except Exception:
                pass

        items.append({
            "url": url,
            "title": title,
            "author": author,
            "published_at": now_iso,
            "content_text": content_text,
            "content_html": content_html,
            "can_publish_fulltext": can_full,
            "source_label": f"GitHub: {owner}/{repo}"
        })
    return items
