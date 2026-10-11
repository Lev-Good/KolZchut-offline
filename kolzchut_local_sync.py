#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
סנקרון מקומי מהמחשב הביתי — הריצה היומית שמחליפה את GitHub Actions.

רצף:
  1. kolzchut_sync_delta.py  — מוריד רק דפים שהשתנו מאז last_sync.txt
  2. kolzchut_remove_content.py --default-charedi-list  — סינון תכנים
  3. kolzchut_build_portal.py --github-repo Lev-Good/KolZchut-offline
  4. קומיט + push של kolzchut_out לגיט (דרך LFS)
  5. gh workflow run "Build release from committed archive"  — מפרסם ZIP חדש

הרצה:  python kolzchut_local_sync.py           (רץ רק אם יש שינויים)
        python kolzchut_local_sync.py --force   (רץ בכל מקרה)
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
    parser.add_argument("--force", action="store_true", help="sync+release even with no changes")
    args = parser.parse_args()

    t0 = time.time()

    # 1) delta sync
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
