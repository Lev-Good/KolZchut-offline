#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Content removal tool for the offline KolZchut archive.

Two modes (can be combined):
  --remove-pages  "title1" "title2"     -> page file removed entirely
  --blank-pages   "title3"              -> page emptied (title kept, no text)
  --remove-words  "word1" "word2"       -> keyword scrub across ALL pages

Keyword mode: a page where ALL keywords match is removed; a page where only
some matches, those <p> paragraphs are removed. Keywords support simple
Hebrew morphology: use the root e.g. "עריות" also covers "העריות".
Matching is substring-based, case-insensitive, across the rendered text.

Usage examples:
  python kolzchut_remove_content.py --remove-pages "טקסט פוגעני" --blank-pages "דף רגיש"
  python kolzchut_remove_content.py --remove-words "הזכרת שם מושחת"
  python kolzchut_remove_content.py --default-charedi-list
  python kolzchut_remove_content.py --default-charedi-list --out kolzchut_out_verified/kolzchut_out

--out exists so CI can run the *real* filter against the submitted archive copy
(see .github/workflows/pr-check.yml): the filter must be a no-op there, which
proves the contributor applied it before submitting.
"""

import argparse
import json
from pathlib import Path

from bs4 import BeautifulSoup

OUT_DEFAULT = Path("kolzchut_out")


def load_index(out: Path):
    return json.loads((out / "index.json").read_text(encoding="utf-8"))


def save_index(index, out: Path):
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                    encoding="utf-8")


def page_text_contains(soup, keyword: str) -> bool:
    text = soup.get_text(" ", strip=True).lower()
    return keyword.lower() in text


def remove_keyword_paragraphs(soup, keyword: str) -> int:
    """Remove <p>/<li> elements that contain the keyword. Returns removal count."""
    removed = 0
    for el in soup.find_all(["p", "li"]):
        if keyword.lower() in el.get_text(" ", strip=True).lower():
            # If a parent LI, remove the whole LI (cleaner rendering)
            if el.name == "li":
                li_ancestor = el
            else:
                li_ancestor = el.find_parent("li")
            to_remove = li_ancestor or el
            to_remove.decompose()
            removed += 1
    return removed


BLANK_PAGE_BODY = "<p><em>תוכן דף זה הוסר מהארכיון.</em></p>"


def main():
    parser = argparse.ArgumentParser(description="Remove problematic content from archive")
    parser.add_argument("--remove-pages", nargs="*", default=[], metavar="TITLE")
    parser.add_argument("--blank-pages", nargs="*", default=[], metavar="TITLE")
    parser.add_argument("--remove-words", nargs="*", default=[], metavar="KEYWORD")
    parser.add_argument("--default-charedi-list", action="store_true",
                        help="apply the built-in sensitive-content list")
    parser.add_argument("--out", default=str(OUT_DEFAULT),
                        help="archive directory to operate on (default kolzchut_out)")
    args = parser.parse_args()

    out = Path(args.out)
    index_file = out / "index.json"
    pages_dir = out / "pages"
    removed_log_file = out / "removed_log.json"

    if not index_file.exists():
        raise SystemExit(f"{index_file} not found - run downloader first")

    index = load_index(out)
    title_to_slug = {t: m.get("slug", "") for t, m in index.items()}

    log = {"removed_pages": [], "blanked_pages": [], "keyword_hits": {}}

    # ---- exact-title removal / blanking
    for mode, titles in (("remove", args.remove_pages), ("blank", args.blank_pages)):
        for title in titles:
            slug = title_to_slug.get(title)
            if not slug:
                print(f"  ! not in index: {title}")
                continue
            p = pages_dir / slug
            if not p.exists():
                continue
            if mode == "remove":
                p.unlink()
                index.pop(title, None)
                log["removed_pages"].append(title)
            else:
                html_text = p.read_text(encoding="utf-8")
                soup = BeautifulSoup(html_text, "html.parser")
                content = soup.find("div", class_="mw-parser-output") or soup.body
                if content:
                    content.clear()
                    content.append(BeautifulSoup(BLANK_PAGE_BODY, "html.parser"))
                    p.write_text(str(soup), encoding="utf-8")
                log["blanked_pages"].append(title)
            print(f"  {mode}: {title}")

    # ---- keyword scrub
    if args.remove_words or args.default_charedi_list:
        keywords = list(args.remove_words)
        if args.default_charedi_list:
            # Built-in starter list; edit freely in a text file and pass --remove-words.
            keywords += [
                "להט\"ב", "טרנסג'נדר", "הפלה מלאכותית", "ניאוף",
                "עובר לסורגן", "גילוי עריות", "רומן מחוץ לנישואין",
                "התאבדות", "פורנוגרפיה",
            ]
        keywords = sorted(set(keywords))

        for title, meta in list(index.items()):
            slug = meta.get("slug", "")
            if not slug:
                continue
            p = pages_dir / slug
            if not p.exists():
                continue
            soup = BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")

            hits = [k for k in keywords if page_text_contains(soup, k)]
            if not hits:
                continue

            # ALL keywords hit AND more than one -> remove entire page.
            if len(hits) == len(keywords) and len(keywords) > 1:
                p.unlink()
                index.pop(title, None)
                log["removed_pages"].append(title)
                print(f"  removed (all keywords): {title}")
                continue

            # Partial hits -> scrub matching paragraphs.
            para_removed = 0
            for k in hits:
                para_removed += remove_keyword_paragraphs(soup, k)
            if para_removed:
                p.write_text(str(soup), encoding="utf-8")
                log["keyword_hits"][title] = {"keywords": hits, "paragraphs_removed": para_removed}
                print(f"  scrubbed {para_removed} paragraphs in: {title} (hits: {hits})")

    save_index(index, out)
    removed_log_file.write_text(json.dumps(log, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    print(f"Log: {removed_log_file}  |  removed={len(log['removed_pages'])} "
          f"blanked={len(log['blanked_pages'])} pages_scrubbed={len(log['keyword_hits'])}")


if __name__ == "__main__":
    main()
