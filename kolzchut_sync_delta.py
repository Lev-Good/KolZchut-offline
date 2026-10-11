#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KolZchut delta sync.
Uses MediaWiki recentchanges to detect pages changed since the last sync,
downloads ONLY those pages, and emits a delta manifest for release tooling.

Usage:
  python kolzchut_sync_delta.py            # normal sync (incremental)
  python kolzchut_sync_delta.py --full     # ignore last_sync, touch nothing
  python kolzchut_sync_delta.py --days 7   # sync edits from the last 7 days
"""

import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

# Reuse the downloader module for API access, cleaning, and file naming.
import kolzchut_download as dl

OUT = Path("kolzchut_out")
PAGES = OUT / "pages"
LAST_SYNC_FILE = OUT / "last_sync.txt"
DELETED_FILE = OUT / "deleted_pages.json"
DELTA_FILE = OUT / "delta.json"
INDEX_FILE = OUT / "index.json"


def load_sync_state():
    """Read last sync timestamp (ISO 8601) from disk."""
    if LAST_SYNC_FILE.exists():
        return LAST_SYNC_FILE.read_text(encoding="utf-8").strip()
    return None


def save_sync_state(timestamp: str):
    LAST_SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_SYNC_FILE.write_text(timestamp, encoding="utf-8")


def fetch_changed_titles(since: str, until: str | None = None):
    """Return set of (ns0) page titles edited since `since`.

    Walks recentchanges backwards with rcdirection=older until we cover the
    window, de-duplicating by title. Only edits/uploads in ns=0 (content).
    """
    changed = set()
    deleted = set()
    rccontinue = None

    params_base = {
        "action": "query",
        "list": "recentchanges",
        "rcstart": until or "now",
        "rcend": since,
        "rcdir": "older",          # newest -> oldest within the window
        "rcprop": "title|ids|timestamp|loginfo",
        "rclimit": "max",
        "rctype": "edit|new|log",  # edits, new pages, and deletes (log)
        "rcnamespace": "0",
    }

    while True:
        params = dict(params_base)
        if rccontinue:
            params["rccontinue"] = rccontinue
        data = dl.api_get(params)

        for rc in data.get("query", {}).get("recentchanges", []):
            title = rc.get("title")
            if not title:
                continue
            if rc.get("revid", 0) == 0 or rc.get("type") == "log":
                # Log entry: may be a delete (page gone) or a move.
                logtype = rc.get("logtype", "")
                if logtype == "delete":
                    deleted.add(title)
                continue
            changed.add(title)

        cont = data.get("continue", {}).get("rccontinue")
        if not cont:
            break
        rccontinue = cont

    return changed, deleted


def main():
    parser = argparse.ArgumentParser(description="KolZchut delta sync")
    parser.add_argument("--full", action="store_true",
                        help="full re-download regardless of last sync")
    parser.add_argument("--days", type=float, default=0,
                        help="sync edits from the last N days instead of last_sync")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    out = Path(args.out)
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    if args.full:
        module_out = args.out
    else:
        last_sync = load_sync_state()
        if not last_sync and not args.days:
            print("No last_sync.txt found. First run detected -> treating as FULL sync.")
            args.full = True
        elif args.days:
            since_ts = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(time.time() - args.days * 86400))
            last_sync = since_ts

    print(f"Sync window: since={last_sync if not args.full else '(full)'}")

    if args.full:
        # Delegate to the main downloader (which handles resume via index.json).
        sys.argv = ["kolzchut_download.py", "--out", args.out]
        dl.main()
        save_sync_state(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        return

    # ---------------- delta path ----------------
    index_path = INDEX_FILE
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}

    known_titles = set(index.keys())
    title_to_file = {t: meta["slug"] for t, meta in index.items()}
    # Titles that may exist on disk but not in our local index yet
    known_titles.update(title_to_file)

    changed, deleted = fetch_changed_titles(last_sync)

    # A page in `deleted` that we have locally, and that wasn't re-edited
    # afterwards, should be removed.
    to_delete = deleted - changed
    # Only delete pages we actually have.
    to_delete = {t for t in to_delete if (pages_dir / title_to_file.get(t, "")).exists()}

    new_or_changed = changed - to_delete

    print(f"Changed/new pages:  {len(new_or_changed)}")
    print(f"Deleted pages:      {len(to_delete)}")

    delta_info = {"since": last_sync, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "changed": [], "deleted": []}

    # ---- Apply deletions
    for title in sorted(to_delete):
        slug = title_to_file.get(title)
        if slug:
            p = pages_dir / slug
            if p.exists():
                p.unlink()
            index.pop(title, None)
            delta_info["deleted"].append(title)

    # ---- Download changed pages (reuse downloader logic)
    t0 = time.time()
    done = failed = 0
    for i, title in enumerate(sorted(new_or_changed), 1):
        slug = title_to_file.get(title) or dl.make_filename(title)
        try:
            raw = dl.fetch_page_html(title)
        except RuntimeError as exc:
            print(f"  !! FAILED: {title}: {exc}", file=sys.stderr)
            failed += 1
            continue

        if raw is None:
            failed += 1
            continue

        body = dl.clean_page_html(raw, title_to_file)
        page = dl.PAGE_TEMPLATE.format(title=title, body=body)
        (pages_dir / slug).write_text(page, encoding="utf-8")
        index[title] = {"slug": slug, "status": "ok", "bytes": len(page)}
        title_to_file[title] = slug
        done += 1
        delta_info["changed"].append(title)

    delta_info["counts"] = {"changed": done, "failed": failed, "deleted": len(to_delete)}
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.out == str(OUT):
        DELTA_FILE.write_text(json.dumps(delta_info, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Done in {time.time()-t0:.0f}s: changed={done}, failed={failed}, deleted={len(to_delete)}")
    print(f"Delta manifest: {DELTA_FILE}")

    # Update the sync cursor AFTER a successful run.
    save_sync_state(delta_info["fetched_at"])


if __name__ == "__main__":
    main()
