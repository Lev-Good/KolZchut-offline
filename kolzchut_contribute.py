#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kolzchut_contribute.py — distributed update submission for authorized editors.

Flow: preflight (base is current + gh identity) → local delta-sync against the
KolZchut sitemap → content-filter → portal rebuild → integrity verification →
commit on a dedicated branch → open a Pull Request. NO direct push to master,
no shared tokens — everything uses the personal GitHub CLI identity
(`gh auth status`) of the contributor.

Never publishes a partial run: a sync with failed>0 aborts before anything is
committed. The PR carries delta.json, so CI re-checks the same numbers.

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
    if isinstance(cmd, str):
        cmd = ["bash", "-lc", cmd]
        kw.pop("shell", None)
    elif not isinstance(cmd, list):
        raise TypeError(f"cmd must be str or list, got {type(cmd)!r}")
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        raise SystemExit(f"Command failed (exit {r.returncode}): {cmd}")


def output(cmd) -> str:
    """Run a command and return stripped stdout (''' on failure)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def get_local_required(what):
    """Ensure required tools are present (single-user CLI context)."""
    if what == "gh":
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(
                "GitHub CLI not authenticated — run `gh auth login` as the "
                "individual user, NOT with a shared token.")


def ensure_base_is_current(base: str) -> bool:
    """True when local HEAD already contains every commit of origin/<base>.

    The delta is computed against the local archive, so a stale base would
    produce a PR that branch protection rejects (required checks are 'strict').
    Detecting it up front avoids an hour of pointless downloading.
    """
    run(["git", "fetch", "origin", base])
    behind = output(["git", "rev-list", "--count", f"HEAD..origin/{base}"])
    if behind and int(behind) > 0:
        print(f"\n!! origin/{base} has {behind} commit(s) you do not have yet.\n"
              f"   Your local archive would be synced against a stale snapshot.\n"
              f"   Update first, then re-run:\n"
              f"     git checkout {base} && git pull --ff-only\n"
              f"     python kolzchut_contribute.py\n", file=sys.stderr)
        return False
    return True


def ensure_label():
    """Make sure the auto-merge label exists (it gates the whole pipeline)."""
    r = subprocess.run(
        ["gh", "label", "create", LABEL_CANDIDATE, "--repo", REPO,
         "--color", "0e8a16", "--force",
         "--description", "Verified archive PR — auto-merged when CI checks pass"],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"note: could not ensure label '{LABEL_CANDIDATE}': "
              f"{(r.stderr or '').strip()}", file=sys.stderr)


def preflight_have_changes() -> tuple[int, int, int]:
    """Read delta.json counts; return (changed, deleted, failed)."""
    if not DELTA_FILE.exists():
        return 0, 0, 0
    d = json.loads(DELTA_FILE.read_text(encoding="utf-8"))
    c = d.get("counts", {})
    return c.get("changed", 0), c.get("deleted", 0), c.get("failed", 0)


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

    # 0) Preflight: a stale base means the local delta is computed against an
    #    out-of-date snapshot — branch protection would reject the result.
    if not ensure_base_is_current(args.base) and not args.check:
        raise SystemExit("aborted: base branch is stale (nothing was synced)")

    # 1) Delta sync — local, honors robots.txt (Crawl-delay 5) via sync_delta.
    run([sys.executable, "kolzchut_sync_delta.py"])

    changed, deleted, failed = preflight_have_changes()
    print(f"local delta: changed={changed} deleted={deleted} failed={failed}")

    if args.check:
        print("(dry run — nothing committed, no PR opened)")
        return 0

    # Never submit a partial archive (requirement: no partial publication).
    if failed:
        raise SystemExit(
            f"local sync reported {failed} failed page(s) — refusing to open a PR. "
            f"Failures are queued in {OUT / 'retry_queue.json'}; re-run later. "
            f"The last verified archive stays published.")

    if not (changed or deleted or args.force):
        print("No changes since last local sync — nothing to submit. "
              "Use --force to submit anyway.")
        return 0

    # 2) Content filtering — local (CI re-runs the real filter and requires it
    #    to be a no-op, so a skipped filter cannot slip through).
    run([sys.executable, "kolzchut_remove_content.py", "--default-charedi-list"])

    # 3) Portal rebuild — so the index carries the GitHub repo update-check.
    run([sys.executable, "kolzchut_build_portal.py", "--github-repo", REPO])

    # 4) Integrity verification — abort on failure (never publish broken state).
    run([sys.executable, "kolzchut_verify.py"])

    # 5) Git identity: the contributor's own git/gh identity, no shared tokens.
    #    HEAD already contains origin/<base> (see preflight), so the switch to a
    #    new branch preserves the freshly synced working tree.
    branch = f"sync/auto-update-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    run(["git", "checkout", "-B", branch])
    run(["git", "add", "kolzchut_out"])
    run(["git", "commit", "-m",
         f"Archive update: {changed} changed, {deleted} deleted "
         f"({time.strftime('%Y-%m-%d %H:%M')})"])
    run(["git", "push", "origin", branch, "--no-verify"])

    # 6) Open PR with the auto-merge candidate label.
    ensure_label()
    title = f"[auto] Archive sync — {changed} changed, {deleted} deleted"
    body = (
        f"**Automated archive update.**\n\n"
        f"- Source: local delta sync (sitemap-based) on a contributor machine\n"
        f"- Run started: `{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}`\n"
        f"- Base at submission: `origin/{args.base}` (verified up to date)\n"
        f"- Pages changed: **{changed}**\n"
        f"- Pages deleted (verified 404 on the live site): **{deleted}**\n"
        f"- Sync failures: **{failed}** (must be 0)\n"
        f"- Content filter: applied locally; CI re-applies it and requires a no-op\n"
        f"\nCI verifies archive integrity from the trusted scripts on `{args.base}`\n"
        f"(`kolzchut_verify.py --baseline origin/{args.base} --require-baseline`).\n"
        f"On success: auto-merge → release build → published ZIP.\n"
        f"On failure nothing is published and the last verified archive stays live.\n"
    )
    run(["gh", "pr", "create",
         "--repo", REPO,
         "--base", args.base,
         "--head", branch,
         "--title", title,
         "--body", body,
         "--label", LABEL_CANDIDATE])

    url = output(["gh", "pr", "view", branch, "--repo", REPO, "--json", "url",
                  "--jq", ".url"])
    if url:
        print(f"\nPR: {url}")
    print(f"PR submitted in {time.time()-t0:.0f}s — CI decides whether to merge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
