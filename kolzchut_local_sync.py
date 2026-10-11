#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local machine sync — daily run supporting the DISTRIBUTED (contributor-PR) model.

מיושן בגרסתו הקודמת (דחיפה ישירה ל-master) — עכשיו ברירת המחדל יוצרת branch
+ PR, ו-CI מחליט האם לאחד ולפרסם (kolzchut_contribute.py). הפצה ישירה נשארת
זמינה דרך  kolzchut_local_sync.py --direct  (לא מומלץ יותר).

New flow (recommended):
  python kolzchut_local_sync.py           → defers to kolzchut_contribute.py

Legacy direct mode (kept for backward compatibility, bypasses PR/CI):
  python kolzchut_local_sync.py --direct

Legacy direct flow:
  1. kolzchut_sync_delta.py  — only changed pages since last_sync.txt
  2. kolzchut_remove_content.py --default-charedi-list  — content filter
  3. kolzchut_build_portal.py --github-repo Lev-Good/KolZchut-offline
  4. commit + push kolzchut_out via git (through LFS)
  5. gh workflow run "Build release from committed archive"  — publish new ZIP
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = "Lev-Good/KolZchut-offline"
OUT = Path("kolzchut_out")
DELTA_FILE = OUT / "delta.json"
RELEASE_WORKFLOW = "Build release from committed archive"


def run(cmd, **kw):
    """Run a command, raising on non-zero exit.

    Accepts either a list (preferred) or a shell string. A shell string is run
    through `bash -lc`; passing shell=True for a list is a caller error that
    used to raise TypeError before anything ran.
    """
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    if isinstance(cmd, str):
        cmd = ["bash", "-lc", cmd]
        kw.pop("shell", None)
    elif not isinstance(cmd, list):
        raise TypeError(f"cmd must be str or list, got {type(cmd)!r}")
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        raise SystemExit(f"Command failed (exit {r.returncode}): {cmd}")


def read_delta_counts() -> dict:
    if not DELTA_FILE.exists():
        return {}
    try:
        return json.loads(DELTA_FILE.read_text(encoding="utf-8")).get("counts", {}) or {}
    except (OSError, ValueError):
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="sync even with no changes")
    parser.add_argument("--direct", action="store_true",
                        help="legacy flow: direct push + release (bypasses PR/CI)")
    args = parser.parse_args()

    t0 = time.time()

    if not args.direct:
        # Recommended path: defer to the distributed (branch + PR) flow.
        fwd = [sys.executable, "kolzchut_contribute.py"]
        if args.force:
            fwd.append("--force")
        run(fwd)
        return

    # 1) delta sync (legacy direct mode)
    run([sys.executable, "kolzchut_sync_delta.py"])

    counts = read_delta_counts()
    changed = counts.get("changed", 0) + counts.get("deleted", 0)
    failed = counts.get("failed", 0)

    if failed:
        raise SystemExit(
            f"local sync reported {failed} failed page(s) — refusing to publish a "
            f"partial archive. Failures are queued in {OUT / 'retry_queue.json'}; "
            f"re-run when connectivity is back.")

    if not changed and not args.force:
        print(f"\nNo changes since last sync — nothing to do. ({time.time()-t0:.0f}s)")
        return

    # 2) content filtering
    run([sys.executable, "kolzchut_remove_content.py", "--default-charedi-list"])

    # 3) portal rebuild
    run([sys.executable, "kolzchut_build_portal.py", "--github-repo", REPO])

    # 4) commit + push archive via LFS
    run("git lfs track 'kolzchut_out/pages/**'")
    run(["git", "add", "kolzchut_out"])
    run(["git", "commit", "-m", f"Archive update: {changed} pages changed "
                               f"({time.strftime('%Y-%m-%d %H:%M')})"])
    run(["git", "push"])

    # 5) trigger release workflow
    run(["gh", "workflow", "run", RELEASE_WORKFLOW, "--repo", REPO])

    print(f"\nDone in {time.time()-t0:.0f}s. Release will appear in a few minutes at:")
    print(f"  https://github.com/{REPO}/releases")


if __name__ == "__main__":
    main()
