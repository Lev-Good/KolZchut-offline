#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KolZchut (כל זכות) offline downloader.
Fetches page text via MediaWiki Action API and builds a clean static archive:
text and links only - no images, no site chrome.

Usage:
  python kolzchut_download.py --limit 50          # pilot: first 50 pages
  python kolzchut_download.py                     # full run (resumes automatically)
  python kolzchut_download.py --out kolzchut_out  # custom output dir
"""

import argparse
import json
import os
import hashlib
import re
import sys
import time
import hashlib
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

API = "https://www.kolzchut.org.il/w/he/api.php"
SITE = "https://www.kolzchut.org.il"
SITEMAP_URL = SITE + "/sitemap/sitemap-kz_he-NS_0-0.xml.gz"
USER_AGENT = "KolZchutOfflineArchive/1.0 (personal non-commercial use; CC-BY-NC-SA-2.5-IL)"
REQUEST_DELAY = 0.15          # polite default for API calls
SITEMAP_DELAY = 5.0           # robots.txt Crawl-delay: 5s for crawler endpoints
MAX_RETRIES = 4
SEEK_DIR = Path("kolzchut_out")

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


# ----------------------------------------------------------------------------- API

def api_get(params: dict, retries: int = MAX_RETRIES):
    """GET the Action API with retries and a polite delay."""
    params = dict(params, format="json", formatversion=2)
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(API, params=params, timeout=30)
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            wait = 2 ** attempt
            print(f"  ! API error (attempt {attempt}/{retries}): {exc} - retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"API call failed after {retries} retries: {params}")


def fetch_page_titles():
    """Return the full list of content-page titles (namespace 0)."""
    titles = []
    apcontinue = None
    while True:
        params = {"action": "query", "list": "allpages", "aplimit": "max",
                  "apnamespace": "0", "apfilterredir": "nonredirects"}
        if apcontinue:
            params["apcontinue"] = apcontinue
        data = api_get(params)
        for page in data["query"]["allpages"]:
            titles.append(page["title"])
        if "continue" in data and data["continue"].get("apcontinue"):
            apcontinue = data["continue"]["apcontinue"]
        else:
            break
    return titles


def fetch_page_html(title: str):
    """Fetch the fully parsed HTML body of one page."""
    data = api_get({"action": "parse", "page": title, "prop": "text", "redirects": "1"})
    if "parse" in data and "text" in data.get("parse", {}):
        return data["parse"]["text"]
    return None


# ------------------------------------------------------------------- sitemap (robots-allowed)

def fetch_sitemap_pages():
    """Fetch the NS0 Hebrew sitemap and return {title: lastmod_iso}.

    Downstream callers treat lastmod as 'modification timestamp of the page
    as declared by the site itself', and compare it against it's stored value
    to detect new / changed / deleted pages.
    """
    import gzip
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(SITEMAP_URL, timeout=120)
            resp.raise_for_status()
            time.sleep(SITEMAP_DELAY)
            data = gzip.decompress(resp.content).decode("utf-8", errors="replace")
            urls = re.findall(r"<loc>(.*?)</loc>", data)
            lastmods = re.findall(r"<lastmod>(.*?)</lastmod>", data)
            pages = {}
            for url, lm in zip(urls, lastmods):
                path = url[len(SITE) + len("/he/"):]
                title = urllib.parse.unquote(path).replace("_", " ")
                pages[title] = lm
            return pages
        except (requests.RequestException, OSError, ValueError) as exc:
            wait = 2 ** attempt * SITEMAP_DELAY
            print(f"  ! sitemap error (attempt {attempt}/{MAX_RETRIES}): {exc} - retrying in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"sitemap fetch failed after {MAX_RETRIES} retries")



def fetch_article_html(title: str):
    """Fetch a page through the public article URL (robots-allowed, edge-cached).

    Returns the inner HTML of div.mw-parser-output, or None when not found.
    Honors the 5 second Crawl-delay via SITEMAP_DELAY.
    """
    url = f"{SITE}/he/{urllib.parse.quote(title.replace(' ', '_'), safe=URL_SAFE)}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=60)
            time.sleep(SITEMAP_DELAY)  # crawl-delay for *all* article requests
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            content = soup.select_one("div.mw-parser-output")
            if content is None:
                return None
            return str(content)
        except requests.RequestException as exc:
            wait = 2 ** attempt * SITEMAP_DELAY
            print(f"  ! article fetch error (attempt {attempt}/{MAX_RETRIES}): {exc} - retrying in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"article fetch failed after {MAX_RETRIES} retries: {title}")


# ----------------------------------------------------------------------------- slugs

SLUG_UNSAFE = re.compile(r'[\\/:*?"<>|]')
MAX_NAME_LEN = 28   # keep total path well under Windows MAX_PATH (260)
# URL-safe characters used in urllib.parse.quote when building article URLs.
URL_SAFE = "()=.~!$&'*+,;:@"

def make_filename(title: str) -> str:
    """Readable Hebrew filename, short, filesystem-safe, collision-free."""
    base = SLUG_UNSAFE.sub("_", title).replace(" ", "_")
    base = base[:MAX_NAME_LEN].rstrip("_")
    digest = hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
    return f"{base}__{digest}.html"


# ----------------------------------------------------------------------------- cleaning

def clean_page_html(raw_html: str, title_to_file: dict):
    """Clean MediaWiki page HTML for offline text+links rendering."""
    soup = BeautifulSoup(raw_html, "html.parser")

    # Remove images / media entirely.
    for tag in soup.find_all(["img", "figure", "figcaption", "video", "audio", "source",
                              "style", "script", "noscript"]):
        tag.decompose()

    # Remove editing section links and other chrome.
    for sel in ["span.mw-editsection", "div.catlinks", "div.mw-references-wrap"]:
        for tag in soup.select(sel):
            tag.decompose()

    # Image-anchored links become plain text.
    for tag in soup.select("a.image"):
        tag.unwrap()

    # Rewrite internal links to local files.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/he/"):
            target = urllib.parse.unquote(href[len("/he/"):])
            frag = ""
            if "#" in target:
                target, frag = target.split("#", 1)
            frag = f"#{frag}" if frag else ""
            # Known pages map to their file; unknown (red links / other wiki-
            # namespace pages) map by hash too, so the link simply 404s locally.
            fname = title_to_file.get(target) or make_filename(target)
            a["href"] = f"pages/{fname}{frag}"
        elif href.startswith("/w/he/index.php"):
            # Special pages / oldid links -> strip to plain text (keep visible label)
            a.unwrap()
        elif href.startswith("//"):
            a["href"] = "https:" + href
        # External http(s) links kept as-is.

    # Drop any leftover empty a tags
    for a in soup.find_all("a"):
        if not a.get_text(strip=True) and not a.find("sup"):
            a.decompose()

    return str(soup)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} – ארכיון כל זכות</title>
<style>
  body {{ font-family: "Segoe UI", "Arial", sans-serif; line-height: 1.65;
         max-width: 48em; margin: 0 auto; padding: 1.5em; color: #222; }}
  h1 {{ font-size: 1.6em; border-bottom: 2px solid #2a6dbd; padding-bottom: .25em; }}
  a {{ color: #2a6dbd; }}
  .topnav {{ font-size: .85em; margin-bottom: 1em; }}
  .credit {{ font-size: .78em; color: #666; border-top: 1px solid #ddd;
            margin-top: 2.5em; padding-top: .5em; }}
</style>
</head>
<body>
<div class="topnav"><a href="index.html">→ חזרה לאינדקס</a></div>
<h1>{title}</h1>
{body}
<p class="credit">מקור: דף “{title}” באתר כל זכות (kolzchut.org.il), אוחזר ב־11.10.2026,
רישיון CC-BY-NC-SA-2.5-IL — שימוש מסחרי אסור.</p>
</body>
</html>
"""


def landing(title: str, reason: str) -> str:
    return PAGE_TEMPLATE.format(title=title,
                                body=f"<p><em>{reason}</em></p>",
                               )


# ----------------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="KolZchut offline downloader")
    parser.add_argument("--limit", type=int, default=0,
                        help="process only the first N pages (0 = all)")
    parser.add_argument("--out", default=str(SEEK_DIR), help="output directory")
    args = parser.parse_args()

    out = Path(args.out)
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    print("1) Fetching full page list via API ...")
    titles = fetch_page_titles()
    print(f"   -> {len(titles)} content pages")
    known_titles = set(titles)
    title_to_file = {t: make_filename(t) for t in known_titles }

    # Build index.json so every static page can link to a consistent lookup later.
    if args.limit:
        titles = titles[: args.limit]
        print(f"   -> PILOT: limited to first {len(titles)} pages")

    index_path = out / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}

    done = failed = 0
    t0 = time.time()
    for i, title in enumerate(titles, 1):
        slug = make_filename(title)
        target = pages_dir / slug
        if target.exists() and index.get(title, {}).get("status") == "ok":
            done += 1
            continue

        try:
            raw = fetch_page_html(title)
        except RuntimeError as exc:
            print(f"  !! [{i}/{len(titles)}] FAILED: {title}: {exc}", file=sys.stderr)
            index[title] = {"slug": slug, "status": "failed"}
            failed += 1
            continue

        if raw is None:
            index[title] = {"slug": slug, "status": "no-content"}
            failed += 1
            continue

        body_html = clean_page_html(raw, title_to_file)
        page = PAGE_TEMPLATE.format(title=title, body=body_html)
        target.write_text(page, encoding="utf-8")

        index[title] = {"slug": slug, "status": "ok", "bytes": len(page)}
        done += 1

        if i % 25 == 0 or i == len(titles):
            index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
            rate = done / max(time.time() - t0, 1)
            remaining = (len(titles) - i) / max(rate, 0.001) / 60
            print(f"   [{i}/{len(titles)}] ok={done} failed={failed} "
                  f"({rate:.1f} pages/s, ~{remaining:.0f} min left)")

    if index_path.exists():
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Done. ok={done} failed={failed}. Index: {index_path}")


if __name__ == "__main__":
    main()
