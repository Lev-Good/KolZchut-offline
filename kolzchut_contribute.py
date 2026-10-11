#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kolzchut_contribute.py — distributed update submission for authorized editors.

Flow: local delta-sync against the KolZchut sitemap → content-filter →
portal rebuild → integrity verification → commit on a dedicated branch →
open a Pull Request. NO direct push to master, no shared tokens — everything
uses the personal GitHub CLI identity (`gh auth status`) of the contributor.

The PR includes machine-readable delta.json and a manifest of changed pages
so CI (kolzchut_verify.py) can compare, filter, and auto-merge on success.

Usage:
  python kolzchut_contribute.py            # sync + open PR if changes exist
  python kolzchut_contribute.py --check    # dry-run: show what would change
  python kolzchut_contribute.py --force    # open PR even with 0 changed pages
  python kolzchut_contribute.py --base BRANCH   # target branch (default master)
"""

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = "Lev-Good/KolZchut-offline"
OUT = Path("kolzchut_out")
DELTA_FILE = OUT / "delta.json"
LABEL_CANDIDATE = "auto-merge-candidate"


def run(cmd, **kw):
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    r = subprocess.run(cmd, shell=isinstance(cmd, str), **kw)
    if r.returncode != 0:
        raise SystemExit(f"Command failed (exit {r.returncode}): {cmd}")


def get_local_required(what):
    """Ensure required tools are present (single-user CLI context)."""
    if what == "gh":
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(
                "GitHub CLI not authenticated — run `gh auth login` as the "
                "individual user, NOT with a shared token.")


def preflight_have_changes() -> tuple[int, int]:
    """Read delta.json counts; return (changed, deleted)."""
    if not DELTA_FILE.exists():
        return 0, 0
    d = json.loads(DELTA_FILE.read_text(encoding="utf-8"))
    c = d.get("counts", {})
    return c.get("changed", 0), c.get("deleted", 0)


def main():
    parser = argparse.ArgumentParser(description="KolZchut distributed contributor flow")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="dry run: show what would change, no PR opened")
    parser.add_argument("--base", default="master",
                        help="base branch to open the PR against")
    args = parser.parse_args()

    t0 = time.time()
    get_local_required("gh")

    # 1) Delta sync — local, honors robots.txt (Crawl-delay 5) via sync_delta.
    run([sys.executable, "kolzchut_sync_delta.py"])

    changed, deleted = preflight_have_changes()
    print(f"local delta: changed={changed} deleted={deleted}")

    if args.check:
        print("(dry run — nothing committed, no PR opened)")
        return 0

    if not (changed or deleted or args.force):
        print("No changes since last local sync — nothing to submit. "
              "Use --force to submit anyway.")
        return 0

    # 2) Content filtering — local (CI re-runs the same filter before merging).
    run([sys.executable, "kolzchut_remove_content.py", "--default-charedi-list"])

    # 3) Portal rebuild — so the index carries the GitHub repo update-check.
    run([sys.executable, "kolzchut_build_portal.py", "--github-repo", REPO])

    # 4) Integrity verification — abort on failure (never publish broken state).
    run([sys.executable, "kolzchut_verify.py"])

    # 5) Git identity: use the user's own git/gh identity, no shared tokens.
    branch = f"sync/auto-update-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"

    run("git lfs track kolzchut_out/pages/** "
        "|| git lfs track 'kolzchut_out/pages/**'", shell=True)
    run("git fetch origin master", shell=True)
    run(f"git checkout -B {branch} origin/master", shell=True)
    run(["git", "add", "kolzchut_out"])
    run(["git", "commit", "-m",
         f"Archive update: {changed} changed, {deleted} deleted "
         f"({time.strftime('%Y-%m-%d %H:%M')})"])
    run(["git", "push", "origin", branch, "--no-verify"])

    # 6) Open PR with the auto-merge candidate label.
    title = f"[auto] Archive sync — {changed} changed, {deleted} deleted"
    body = (
        f"**Automated archive update.**\n\n"
        f"- Source: local delta sync (sitemap-based) on a contributor machine\n"
        f"- Run started: `{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}`\n"
        f"- Pages changed: **{changed}**\n"
        f"- Pages deleted (verified 404): **{deleted}**\n"
        f"- Content filter: applied locally; CI re-applies it before merge\n"
        f"\nCI will verify archive integrity (`kolzchut_verify.py --baseline origin/master`).\n"
        f"On success the sequence is: merge → release build → publish ZIP.\n"
        f"On failure nothing is published and the last successful archive stays live.\n"
    )
    run(["gh", "pr", "create",
         "--repo", REPO,
         "--base", args.base,
         "--head", branch,
         "--title", title,
         "--body", body,
         "--label", LABEL_CANDIDATE])

    run(["gh", "pr", "view", "--json", "url", "--jq", ".url"])
    print(f"\nPR submitted in {time.time()-t0:.0f}s — CI decides whether to merge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
