#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package the offline archive into a release ZIP + manifest.json.

manifest.json holds one sha256 per downloaded page so a future local updater
can verify which pages are outdated without comparing full files.

Usage:
  python kolzchut_release.py                 # build release from kolzchut_out
  python kolzchut_release.py --out-dir dist  # custom output dir
"""

import argparse
import hashlib
import json
import time
import zipfile
from pathlib import Path

OUT = Path("kolzchut_out")
RELEASES = Path("releases")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Package KolZchut release")
    parser.add_argument("--out-dir", default=str(RELEASES))
    args = parser.parse_args()

    out = OUT
    if not (out / "index.json").exists():
        raise SystemExit("kolzchut_out/index.json not found - run downloader first")

    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    ok_pages = {t: m for t, m in index.items() if m.get("status") == "ok"}
    print(f"Packaging {len(ok_pages)} pages")

    pages_dir = out / "pages"

    # -------- manifest with per-page hashes --------
    manifest = {
        "version": time.strftime("v%Y%m%d", time.gmtime()),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "page_count": len(ok_pages),
        "pages": {},
        "delta": None,
    }
    delta_path = out / "delta.json"
    if delta_path.exists():
        manifest["delta"] = json.loads(delta_path.read_text(encoding="utf-8"))

    for title, meta in sorted(ok_pages.items()):
        p = pages_dir / meta["slug"]
        if p.exists():
            manifest["pages"][title] = {"slug": meta["slug"], "sha256": file_sha256(p)}

    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    # -------- zip --------
    zpath = Path(args.out_dir) / f"kolzchut_{manifest['version']}.zip"
    zpath.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out))

    print(f"ZIP:    {zpath}  ({zpath.stat().st_size/1_048_576:.1f} MB)")
    print(f"manifest.json: {out/'manifest.json'}")


if __name__ == "__main__":
    main()
