#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package the KolZchut offline archive into a standard .ZIM file for Kiwix.
Uses libzim to produce a highly-compressed, searchable offline archive.
"""

import json
import os
import sys
import time
from pathlib import Path
from libzim.writer import Creator, Item, FileProvider, StringProvider

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "kolzchut_out"
PAGES_DIR = OUT_DIR / "pages"
RELEASES_DIR = BASE_DIR / "releases"


class ZimFileItem(Item):
    def __init__(self, path: str, title: str, file_path: Path, mimetype: str = "text/html; charset=utf-8"):
        super().__init__()
        self._path = path
        self._title = title
        self._file_path = str(file_path)
        self._mimetype = mimetype

    def get_path(self) -> str:
        return self._path

    def get_title(self) -> str:
        return self._title

    def get_mimetype(self) -> str:
        return self._mimetype

    def get_contentprovider(self):
        return FileProvider(self._file_path)

    def get_hints(self) -> dict:
        return {}


def build_zim(output_path: Path):
    if not (OUT_DIR / "index.json").exists():
        print(f"Error: {OUT_DIR / 'index.json'} not found.")
        sys.exit(1)

    index_data = json.loads((OUT_DIR / "index.json").read_text(encoding="utf-8"))
    ok_pages = {t: m for t, m in index_data.items() if m.get("status") == "ok"}

    print(f"Packaging {len(ok_pages)} pages into ZIM format...")
    print(f"Destination: {output_path}")

    if output_path.exists():
        output_path.unlink()

    creator = Creator(output_path)
    creator.config_indexing(True, "heb")
    creator.config_nbworkers(4)

    t0 = time.time()
    with creator:
        creator.set_mainpath("index.html")
        creator.add_metadata("Title", "כל זכות (KolZchut)")
        creator.add_metadata("Description", "מאגר המידע המלא לזכויות בישראל מבית כל-זכות")
        creator.add_metadata("Language", "heb")
        creator.add_metadata("Creator", "כל-זכות (kolzchut.org.il)")
        creator.add_metadata("Publisher", "KolZchut Offline Project")
        creator.add_metadata("Date", time.strftime("%Y-%m-%d"))

        # Add index.html
        if (OUT_DIR / "index.html").exists():
            creator.add_item(ZimFileItem("index.html", "כל זכות - דף הבית", OUT_DIR / "index.html"))

        # Add all pages
        count = 0
        for title, meta in ok_pages.items():
            slug = meta.get("slug")
            if not slug:
                continue
            page_path = PAGES_DIR / slug
            if page_path.exists():
                # In ZIM, path can be the slug directly
                creator.add_item(ZimFileItem(f"pages/{slug}", title, page_path))
                # Also add direct slug without pages/ prefix so both resolve
                creator.add_item(ZimFileItem(slug, title, page_path))
                count += 1
                if count % 1000 == 0:
                    print(f"  Indexed {count}/{len(ok_pages)} pages...")

    elapsed = time.time() - t0
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print("=" * 60)
    print(f"ZIM Archive created successfully in {elapsed:.1f}s!")
    print(f"Output: {output_path} ({size_mb:.1f} MB)")
    print("=" * 60)


def main():
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = time.strftime("v%Y%m%d")
    zim_path = RELEASES_DIR / f"kolzchut_he_all_{date_tag}.zim"
    build_zim(zim_path)


if __name__ == "__main__":
    main()
