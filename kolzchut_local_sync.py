#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local machine sync — daily run supporting the DISTRIBUTED (contributor-PR) model.

⚠️  מיושן בגרסתו הקודמת (דחיפה ישירה ל-master) — עכשיו ברירת המחדל יוצרת branch
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


def run(cmd, **kw):
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    r = subprocess.run(cmd, shell=isinstance(cmd, str), **kw)
    if r.returncode != 0:
        raise SystemExit(f"Command failed: {cmd}")


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

    changed = 0
    if DELTA_FILE.exists():
        d = json.loads(DELTA_FILE.read_text(encoding="utf-8"))
        changed = d.get("counts", {}).get("changed", 0) + d.get("counts", {}).get("deleted", 0)

    if not changed and not args.force:
        print(f"\nNo changes since last sync — nothing to do. ({time.time()-t0:.0f}s)")
        return

    # 2) content filtering
    run([sys.executable, "kolzchut_remove_content.py", "--default-charedi-list"])

    # 3) portal rebuild
    run([sys.executable, "kolzchut_build_portal.py", "--github-repo", REPO])

    # 4) commit + push archive via LFS
    run("git lfs track kolzchut_out/pages/** "
        "|| git lfs track 'kolzchut_out/pages/**'", shell=True)
    run(["git", "add", "kolzchut_out"])
    run(["git", "commit", "-m", f"Archive update: {changed} pages changed "
                               f"({time.strftime('%Y-%m-%d %H:%M')})"])
    run(["git", "push"])

    # 5) trigger release workflow
    run(["gh", "workflow", "run", "Build release from committed archive", "--repo", REPO])

    print(f"\nDone in {time.time()-t0:.0f}s. Release will appear in a few minutes at:")
    print(f"  https://github.com/{REPO}/releases")


if __name__ == "__main__":
    main()
