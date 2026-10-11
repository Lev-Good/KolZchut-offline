#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the offline portal for the KolZchut archive.

Reads kolzchut_out/index.json (produced by kolzchut_download.py) and writes:
  - kolzchut_out/index.html   : RTL topic-less alpha list + embedded local search
Search data is embedded inline as JSON so it works from file:// without a server.

Usage:  python kolzchut_build_portal.py [--out kolzchut_out]
"""

import argparse
import html
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Build KolZchut offline portal")
    parser.add_argument("--out", default="kolzchut_out")
    parser.add_argument("--github-repo", default="",
                        help="owner/repo for update-check (e.g. myuser/kolzchut-offline)")
    args = parser.parse_args()
    github_repo = args.github_repo

    # Sync-reset: the version comes from the release script if it already ran,
    # otherwise '0' (treated as "no version").
    import time
    manifest_path = Path(args.out) / "manifest.json"
    rel_version = (json.loads(manifest_path.read_text(encoding="utf-8"))["version"]
                   if manifest_path.exists() else time.strftime("v%Y%m%d"))

    out = Path(args.out)
    index_path = out / "index.json"
    if not index_path.exists():
        raise SystemExit(f"index.json not found in {out} - run kolzchut_download.py first")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    ok_items = {t: meta for t, meta in index.items()
                if meta.get("status") == "ok"}
    print(f"Portal: {len(ok_items)} downloadable pages found in index")

    # Embedded search data: [title, filename]. Kept flat & compact.
    search_data = [[t, meta["slug"]] for t, meta in sorted(ok_items.items())]
    search_json = json.dumps(search_data, ensure_ascii=False)

    # Letter-grouped alphabetical listing (Hebrew letters first, then others).
    def first_letter(title: str) -> str:
        t = title.lstrip("\"“' (")
        return t[0] if t else "#"

    groups = {}
    for t in sorted(ok_items):
        groups.setdefault(first_letter(t), []).append(t)

    letters_html = []
    for letter in sorted(groups, key=lambda c: (not ("א" <= c <= "ת"), c)):
        letters_html.append(
            f'<section class="group"><h2 id="l{html.escape(letter)}">{html.escape(letter)}</h2><ul>'
            + "".join(
                f'<li><a href="pages/{html.escape(ok_items[t]["slug"])}">{html.escape(t)}</a></li>'
                for t in sorted(groups[letter])
            )
            + "</ul></section>"
        )

    page = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ארכיון כל זכות – אופליין</title>
<style>
  body { font-family: "Segoe UI", Arial, sans-serif; direction: rtl;
         max-width: 52em; margin: 0 auto; padding: 1.5em; color: #222; }
  h1 { color: #2a6dbd; margin-bottom: .2em; }
  .sub { color: #666; font-size: .9em; margin-bottom: 1.5em; }
  #q { width: 100%; box-sizing: border-box; font-size: 1.15em;
       padding: .55em 1em; border: 2px solid #2a6dbd; border-radius: 8px;
       outline: none; }
  #results { margin-top: 1em; }
  #results li { margin: .35em 0; }
  .group { margin-top: 1.4em; }
  .group h2 { font-size: 1.25em; color: #2a6dbd; border-bottom: 1px solid #ddd;
              padding-bottom: .15em; }
  .group ul { columns: 2 auto; column-gap: 3em; }
  .group li { break-inside: avoid; margin: .25em 0; }
  a { color: #2a6dbd; text-decoration: none; }
  a:hover { text-decoration: underline; }
  footer { margin-top: 3em; border-top: 1px solid #ddd; padding-top: .6em;
           font-size: .78em; color: #666; }
</style>
</head>
<body>
<h1>ארכיון כל זכות – אופליין</h1>
<div class="sub">__NPAGES__ דפי תוכן, אוחזר מ-‎kolzchut.org.il ב־11.10.2026</div>

<input id="q" type="search" autocomplete="off" placeholder="חיפוש בכל הדפים… (לדוגמה: דמי אבטלה)">
<ul id="results" hidden></ul>

<div id="browse">
__GROUPS__
</div>

<footer>
מקור: אתר כל זכות (kolzchut.org.il), רישיון CC-BY-NC-SA-2.5-IL — שימוש מסחרי אסור.
התוכן שונה מגרסת המקור: ללא תמונות וללא תכנים שהוסרו עקב שינויים מקומיים.
</footer>

<script>
const DATA = __DATA__;
const q = document.getElementById('q');
const results = document.getElementById('results');
const browse = document.getElementById('browse');

function norm(s) {
  return s.replace(/["\\u059C\\u05F4'\\u2019\\u201C\\u201D\\u2013\\u2014\\-]/g, ' ')
          .toLowerCase();
}
const normData = DATA.map(([t, f]) => [norm(t), t, f]);

q.addEventListener('input', () => {
  const term = norm(q.value.trim());
  if (term.length < 2) {
    results.hidden = true;
    browse.hidden = false;
    browse.style.display = '';
    return;
  }
  const hits = normData
      .filter(([nt]) => nt.includes(term))
      .slice(0, 200)
      .map(([nt, t, f]) =>
          `<li><a href="pages/${f}">${t}</a></li>`);
  browse.hidden = true;
  results.hidden = false;
  results.innerHTML = hits.length
      ? hits.join('')
      : '<li>לא נמצאו תוצאות…</li>';
});
</script>
<script>
// ---------- עדכונים: בדיקת גרסה מול GitHub Releases ----------
// עדכנו כאן את שם הריפו אחרי העלאה ל-GitHub, לדוגמה: "myuser/kolzchut-offline"
const GITHUB_REPO = "__GITHUB_REPO__";

async function checkForUpdate() {
  if (!GITHUB_REPO || GITHUB_REPO.includes("__")) return; // עדיין לא הוגדר
  try {
    const res = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/releases/latest`);
    if (!res.ok) return;
    const rel = await res.json();
    const latest = (rel.tag_name || "").replace(/v/, "");
    const local = (await (await fetch("version.txt")).text()).trim();
    if (latest && local && latest > local) {
      const bar = document.createElement("div");
      bar.style.cssText = "background:#fff3cd;border:1px solid #ffdf5f;padding:.6em 1em;" +
                          "border-radius:8px;margin-bottom:1.2em;font-size:.95em";
      bar.innerHTML = `קיימת גרסה חדשה (${latest}) של הארכיון – הגרסה המקומית שלך ${local}. ` +
        `<a href="${rel.html_url}" target="_blank">לחצו כאן להורדת העדכון</a>.`;
      document.querySelector("h1").after(bar);
    }
  } catch (e) { /* offline - no problem */ }
}
checkForUpdate();
</script>
</body>
</html>
"""
    page = (page
            .replace("__NPAGES__", str(len(ok_items)))
            .replace("__GROUPS__", "\n".join(letters_html))
            .replace("__DATA__", search_json)
            .replace("__GITHUB_REPO__", github_repo))

    (out / "index.html").write_text(page, encoding="utf-8")
    # version.txt: matches the release tag so in-app update check can compare
    (out / "version.txt").write_text(rel_version, encoding="utf-8")
    print(f"Written: {out/'index.html'}  ({len(page)//1024} KB)")
    print(f"version.txt: {rel_version}")


if __name__ == "__main__":
    main()
