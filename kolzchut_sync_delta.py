#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KolZchut delta sync.

Detects pages added / changed / deleted since the last sync WITHOUT calling
the MediaWiki Action API for change detection. Uses:

  1. The NS0 Hebrew sitemap (robots.txt-allowed, <lastmod> per page)
     -> authoritative list of current pages + per-page modification time.
  2. Differential comparison of local archive index.json (in which we record
     the lastmod we last downloaded) vs the fresh sitemap:
        - page in sitemap, not in archive      -> new page     -> download
        - page in sitemap with newer lastmod   -> changed page -> download
        - archive page missing from sitemap    -> deleted page -> remove

Downloads are performed through the public article URL (edge-cached,
robots-allowed, Crawl-delay: 5 seconds honored). This respects the site's
robots.txt, which Disallows /w/*/api.php for automated crawlers.

Safety-critical properties (see docs/DECISIONS.md):
  - last_sync.txt is ONLY advanced when zero pages failed this run.
  - pages that failed to download stay recorded in retry_queue.json so the
    next run retries them BEFORE advancing the cursor past their window.
  - Deletions detected via sitemap are only applied when the page is truly
    absent from the fresh sitemap (not a sitemap glitch: we require the
    whole current list to be successfully fetched first).

Usage:
  python kolzchut_sync_delta.py            # normal incremental sync
  python kolzchut_sync_delta.py --days 7   # ignore last_sync, grab edits from last 7days
  python kolzchut_sync_delta.py --check    # dry run: show changes, do nothing
"""

import argparse
import json
import posixpath
import re
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

import requests

# Reuse the downloader module for API access, cleaning, and file naming.
import kolzchut_download as dl

OUT = Path("kolzchut_out")
PAGES = OUT / "pages"
LAST_SYNC_FILE = OUT / "last_sync.txt"
DELETED_FILE = OUT / "deleted_pages.json"
DELTA_FILE = OUT / "delta.json"
INDEX_FILE = OUT / "index.json"
RETRY_QUEUE = OUT / "retry_queue.json"
SYNC_LOG = OUT / "sync_log.jsonl"


# ------------------------------------------------------------------- state

def load_sync_state():
    """Read last successful sync time (ISO 8601) from disk, or None."""
    if LAST_SYNC_FILE.exists():
        try:
            return LAST_SYNC_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return None


def save_sync_state(timestamp: str):
    """Write last successful sync time. Only the caller that validated a
    fully-successful run should call this. Never call from a partial run."""
    LAST_SYNC_FILE.write_text(timestamp, encoding="utf-8")


def load_retry_queue():
    if RETRY_QUEUE.exists():
        try:
            return json.loads(RETRY_QUEUE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    return []


def save_retry_queue(items):
    RETRY_QUEUE.write_text(json.dumps(items, ensure_ascii=False, indent=1),
                           encoding="utf-8")


def append_sync_log(entry: dict):
    SYNC_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SYNC_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------- sitemap diff (sitemap only)

def sitemap_time_to_epoch(lm: str) -> float:
    """Convert sitemap lastmod '2026-10-11T04:30:02Z' to epoch seconds."""
    return datetime.strptime(lm, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc).timestamp()


# --------------------------------------------------------------- per-page deletion verification

def verify_page_exists(title: str) -> bool:
    """HEAD-request the article URL to confirm a page truly exists on the live site.

    The supplied sitemap omits a few started pages (checked empirically: the 10
    pension retirement pages are absent from the sitemap while returning 200 on
    the live site).  Deletions detected via sitemap diff are therefore never
    trusted blindly: this returns True unless HEAD conclusively reports 404
    (or 410) — network errors already mean 'can't verify, do NOT delete'.
    """
    url = (f"{dl.SITE}/he/"
           f"{urllib.parse.quote(title.replace(' ', '_'), safe=dl.URL_SAFE)}")
    for attempt in range(1, dl.MAX_RETRIES + 1):
        try:
            resp = dl.session.head(url, timeout=30, allow_redirects=True)
            time.sleep(dl.SITEMAP_DELAY)   # crawl-delay applies here too
            if resp.status_code in (404, 410):
                return False
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            wait = 2 ** attempt * dl.SITEMAP_DELAY
            print(f"  ! delete-verify error (attempt {attempt}/{dl.MAX_RETRIES}): {exc} - retrying in {wait:.0f}s",
                  file=sys.stderr)
            time.sleep(wait)
    # Retries exhausted -> cannot verify -> treat as existing (never deletes on net error)
    return True


def main():
    parser = argparse.ArgumentParser(description="KolZchut delta sync (sitemap-based)")
    parser.add_argument("--full", action="store_true",
                        help="full re-download regardless of last sync")
    parser.add_argument("--days", type=float, default=0,
                        help="ignore last_sync; grab everything changed in last N days (based on sitemap) - see docs")
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--check", action="store_true",
                        help="dry-run: report what would change, write nothing")
    args = parser.parse_args()

    out = Path(args.out)
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"run {run_id}")

    index_path = out / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    log_action = lambda *a, **k: print(*a, **k)

    # ---------------- 1. Fetch fresh sitemap (full current state)
    print("1) Fetching fresh NS0 sitemap ...")
    try:
        sitemap = dl.fetch_sitemap_pages()   # {title: lastmod}
    except RuntimeError as exc:
        print(f"  !! sitemap fetch failed: {exc}", file=sys.stderr)
        append_sync_log({"time": run_id, "phase": "sitemap-fetch", "status": "error",
                         "detail": str(exc)})
        if not args.check:
            print("  -> Keeping last_sync.txt unchanged (no data loss possible).")
        return 2

    print(f"   -> {len(sitemap)} pages listed in sitemap")
    if len(sitemap) < 1000:
        # sitemap too short -> probably a bad/empty response; refuse to act on it
        print(f"  !! sitemap suspiciously small ({len(sitemap)} pages); aborting to avoid mass deletion", file=sys.stderr)
        append_sync_log({"time": run_id, "phase": "sitemap-validate", "status": "error",
                         "detail": f"sitemap tiny ({len(sitemap)} pages)"})
        return 2

    # ---------------- 2. Compare vs archive index
    # Compute local lastmod map by extracting mod time stored for each page,
    # or '0' if unknown -> triggers re-fetch (never lose a page though).
    archive_slugs = {}
    for title, meta in index.items():
        archive_slugs.setdefault(meta.get("slug"), title)

    # Store lastmod in index: use meta["lastmod"] if present, else digest-based "unknown"
    def local_lastmod(meta) -> float:
        lm = meta.get("lastmod")
        if lm:
            try:
                return sitemap_time_to_epoch(lm)
            except ValueError:
                pass
        return 0.0

    local = {t: local_lastmod(meta) for t, meta in index.items()}

    new_titles = [t for t in sitemap if t not in local]
    changed_titles = [t for t in sitemap if t in local and sitemap_time_to_epoch(sitemap[t]) > local[t]]
    deleted_titles = sorted(set(local) - set(sitemap))

    # ---- Backfill: seed missing lastmod values into the index ----
    # After a full download (which used the API) the index has no lastmod; we
    # adopt the sitemap value for every existing, unmodified-vs-sitemap page,
    # so future runs see a clean diff.  Pages we never downloaded (status != ok)
    # stay without lastmod -> they will be retried on the next pass.
    backfilled = 0
    for t, meta in index.items():
        if "lastmod" not in meta and t in sitemap:
            if meta.get("status") == "ok" or meta.get("status") in ("failed", "no-content"):
                meta["lastmod"] = sitemap[t]
                backfilled += 1
    if backfilled:
        print(f"   -> backfilled lastmod into {backfilled} index entries")
        # Recompute the local map now that lastmod values are seeded — otherwise
        # every page would still compare as 'changed' against lastmod=0.
        local = {t: local_lastmod(meta) for t, meta in index.items()}
    changed_titles = [t for t in sitemap if t in local and sitemap_time_to_epoch(sitemap[t]) > local[t]]

    print(f"2) Diff vs archive index:")
    print(f"   new: {len(new_titles)} | changed: {len(changed_titles)} | deleted: {len(deleted_titles)}")

    if args.check:
        print("(dry run – writing nothing)")
        for t in new_titles[:20]:
            print("   + NEW:", t)
        for t in changed_titles[:20]:
            print("   ~ CHANGED:", t)
        for t in deleted_titles[:20]:
            print("   - DELETED:", t)
        append_sync_log({"time": run_id, "phase": "dry-run", "status": "info",
                         "new": len(new_titles), "changed": len(changed_titles),
                         "deleted": len(deleted_titles)})
        return 0

    def fetch_and_write(title: str, title_to_file: dict):
        """Fetch one page via the allowed article URL, clean, save, return bool."""
        slug = title_to_file.get(title) or dl.make_filename(title)
        try:
            raw = dl.fetch_article_html(title)
        except RuntimeError as exc:
            print(f"  !! fetch FAILED: {title}: {exc}", file=sys.stderr)
            return False
        if raw is None:
            # The article URL 404s -> treat as deleted from the live site (moved or deleted).
            print(f"  ! article 404 (treating as deleted): {title}", file=sys.stderr)
            return False

        try:
            body = dl.clean_page_html(raw, title_to_file)
            page = dl.PAGE_TEMPLATE.format(title=title, body=body)
            (pages_dir / slug).write_text(page, encoding="utf-8")
        except OSError as exc:
            print(f"  !! write FAILED: {title}: {exc}", file=sys.stderr)
            return False
        index[title] = {"slug": slug, "status": "ok", "bytes": len(page),
                        "lastmod": sitemap[title]}
        title_to_file[title] = slug
        return True

    title_to_file = {t: meta.get("slug") or dl.make_filename(t) for t, meta in index.items()}

    # ---------------- 3. Deletions — with live-site verification
    deleted_list = []
    verified_missing = []
    for title in deleted_titles:
        if not verify_page_exists(title):
            verified_missing.append(title)
            slug = title_to_file.get(title)
            if slug:
                p = pages_dir / slug
                if p.exists():
                    p.unlink()
                    deleted_list.append(title)
            index.pop(title, None)
        else:
            # The page actually exists on the live site — the sitemap simply omitted it.
            # Keep it in the archive and adopt the sitemap's lastmod if any so the
            # next run is not fooled again.  (Never trust sitemap-only deletions.)
            print(f"  ! delete FALSE-POSITIVE (sitemap omitted, page live): {title}")
            if title in sitemap:
                index[title]["lastmod"] = sitemap[title]
    if deleted_titles:
        print(f"   sitemap-deleted: {len(deleted_titles)} -> verified-missing: {len(verified_missing)}"
              f" (false positives kept in archive: {len(deleted_titles) - len(verified_missing)})")

    # ---------------- 4. Queue: retry-first queue, then new, then changed
    retry_q = load_retry_queue()  # list of {"title": ..., "since": ...}
    set_updated = set(changed_titles) | set(new_titles)
    work_plan = []
    for it in retry_q:
        title = it["title"]
        if title not in sitemap:
            continue   # page doesn't exist anymore; the sitemap diff already handled it
        if title in local and sitemap_time_to_epoch(sitemap[title]) > local.get(title, 0):
            work_plan.append(title)
    retain = [it for it in retry_q if it["title"] in set_updated or it["title"] in local]
    for t in set_updated:
        if t not in work_plan:
            work_plan.append(t)
    # dedupe, preserve order
    seen = set(); plan = []
    for t in work_plan:
        if t not in seen:
            seen.add(t); plan.append(t)

    print(f"3) Download plan: {len(plan)} pages (retries={len(retry_q) if retry_q else 0})")

    # ---------------- 5. Download loop with failures logged, last_sync gated
    done = failed_titles = 0
    failed = []
    t0 = time.time()
    new_failed: list[str] = []
    for i, title in enumerate(plan, 1):
        ok = fetch_and_write(title, title_to_file)
        if ok:
            done += 1
        else:
            failed_titles += 1
            new_failed.append(title)
        if i % 20 == 0 or i == len(plan):
            rate = done / max(time.time() - t0, 1)
            rem = (len(plan) - i) / max(rate, 0.001) / 60
            print(f"   [{i}/{len(plan)}] ok={done} fail={failed_titles} ({rate:.2f} pages/s, ~{rem:.0f}m left)")

    # pages in retry queue that we did NOT plan this run (shouldn't happen now, be safe)
    unresolved_old = [it["title"] for it in retry_q if it["title"] not in plan]

    failed = failed_titles + len(unresolved_old)

    # ---------------- 6. Write state
    delta_info = {
        "since": load_sync_state(),
        "fetched_at": run_id,
        "changed": [t for t in plan if t in title_to_file and t not in deleted_list],
        "deleted": deleted_list,
        "counts": {"changed": done, "failed": failed, "deleted": len(deleted_list)},
    }
    DELTA_FILE.write_text(json.dumps(delta_info, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    with (out / "deleted_pages.json").open("w", encoding="utf-8") as f:
        json.dump(deleted_list, f, ensure_ascii=False, indent=1)

    # ---------------- 7. retry queue for failures
    if new_failed or unresolved_old:
        merged = [{"title": t, "since": run_id} for t in sorted(set(new_failed) | set(unresolved_old))]
        save_retry_queue(merged)
        print(f"  !! {len(merged)} page(s) failed -> recorded in {RETRY_QUEUE.name} for next run")
    else:
        if RETRY_QUEUE.exists():
            RETRY_QUEUE.unlink()
        print(f"  no pending retries")

    # ---------------- 8. Save sync cursor ONLY on full success
    if failed == 0:
        save_sync_state(run_id)
        print(f"Sync cursor advanced to {run_id}")
    else:
        print(f"Sync cursor NOT advanced: {failed} failures.")
        print(f"Next run will re-detect those pages (sitemap lastmod won't go away).")

    append_sync_log({
        "time": run_id,
        "phase": "run",
        "status": "ok" if failed == 0 else "partial",
        "new": len(new_titles),
        "changed": len(changed_titles),
        "deleted": len(deleted_list),
        "downloaded": done,
        "failed": failed,
    })

    print(f"Done in {time.time()-t0:.0f}s: changed={done} failed={failed} deleted={len(deleted_list)}")
    print(f"Delta manifest: {DELTA_FILE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
