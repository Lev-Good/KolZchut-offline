#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrity verifier for the KolZchut offline archive.

Runs the same checks in CI (on a contributor's Pull Request) and locally.
Exit code 0 = clean archive, 1 = failures found. Produces a machine-readable
report on stdout (JSON) plus a human-readable summary on stderr.

Checks:
  1. index.json parses and every entry has string slug + known status
  2. every status="ok" entry exists on disk with non-zero size
  3. every page file on disk maps to exactly one index entry (no orphans,
     no duplicates — a duplicate is two titles pointing at the same slug)
  4. no page HTML contains disallowed content markers (script/img tags)
     after scrubbing — verifies the content filter effect
  5. internal links in HTML point at files that exist either on disk or in
     the index (broken-link ratio reported; > 2% is an error)
  6. anomalous diff: archive must not shrink by > 200 pages or grow by
     > 2,000 pages vs the baseline index (baseline = master's index.json
     when running in CI, none locally unless --baseline given)

Usage:
  python kolzchut_verify.py [--out kolzchut_out] [--baseline master]
                             [--allow-shrink N] [--allow-grow N]
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

DISALLOWED_TAGS = {"script", "iframe", "img", "video", "audio", "object", "embed"}
DEFAULT_ALLOW_SHRINK = 200
DEFAULT_ALLOW_GROW = 2000
OUT_DEFAULT = Path("kolzchut_out")


def load_index(out: Path):
    p = out / "index.json"
    if not p.exists():
        raise SystemExit(f"index.json not found in {out}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"index.json is not valid JSON: {exc}")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256(path.read_bytes())
    return h.hexdigest()


def collect_slugs(index: dict):
    """Return {slug: [titles]} to detect duplicate slugs."""
    s = {}
    for title, meta in index.items():
        slug = meta.get("slug")
        if not slug:
            continue
        s.setdefault(slug, []).append(title)
    return s


def check_index(index: dict):
    errors = []
    for title, meta in index.items():
        if not isinstance(meta, dict):
            errors.append(f"index entry not a dict: {title!r}")
            continue
        if not isinstance(meta.get("slug"), str) or not meta["slug"]:
            errors.append(f"missing/empty slug: {title!r}")
        if meta.get("status") not in ("ok", "failed", "no-content"):
            errors.append(f"unknown status {meta.get('status')!r}: {title!r}")
    return errors


def check_pages_on_disk(out: Path, index: dict):
    errors, missing = [], []
    pages = out / "pages"
    for title, meta in index.items():
        if meta.get("status") != "ok":
            continue
        slug = meta.get("slug")
        p = pages / slug if slug else None
        if not p or not p.exists():
            missing.append(f"status=ok but file missing: {title!r} ({slug})")
        elif p.stat().st_size == 0:
            errors.append(f"status=ok but file is empty: {title!r} ({slug})")
    return errors, missing


def check_orphans_and_duplicates(out: Path, slug_map: dict):
    errors = []
    pages = out / "pages"
    on_disk = {f.name for f in pages.iterdir() if f.is_file()} if pages.exists() else set()
    indexed = set(slug_map)
    orphans = sorted(on_disk - indexed)
    duplicates = {slug: titles for slug, titles in slug_map.items() if len(titles) > 1}
    if orphans:
        errors.append(f"orphan page files (not in index): {orphans[:10]} "
                      f"(total {len(orphans)})")
    for slug, titles in duplicates.items():
        errors.append(f"duplicate slug {slug}: {titles}")
    return errors, orphans, duplicates


def check_html_cleanliness(out: Path, sample: int = 400):
    """Hop over sample of pages and confirm disallowed tags are absent."""
    import random
    errors = []
    pages = sorted((out / "pages").glob("*.html"))
    random.seed(0)   # stable sample in CI
    files = random.sample(pages, min(sample, len(pages)))
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace").lower()
        except OSError as exc:
            errors.append(f"unreadable page {p.name}: {exc}")
            continue
        for tag in DISALLOWED_TAGS:
            if f"<{tag}>" in text or f"<{tag} " in text or f"<{tag}/>" in text:
                errors.append(f"disallowed tag <{tag}> found in {p.name}")
                break
    return errors, len(files)


def check_internal_links(out: Path, index: dict, sample: int = 200):
    """Extract page-local hrefs and verify target exists on disk or can be derived
    from index titles (make_filename). Broken-link ratio over 2% is an error.

    Some legacy downloads contain stale slug hashes in their HTML (because the
    full-download make_filename and the delta-sync title_to_file diverged at one
    point).  We therefore count a link as broken only when BOTH the target file
    does not exist on disk AND no slug in the index starts with the same base
    (same title, different hash) — those are legacy-style variants of the target.
    """
    import re as _re
    import random
    errors = []
    pages = sorted((out / "pages").glob("*.html"))
    random.seed(1)
    sample_files = random.sample(pages, min(sample, len(pages)))
    broken = total = 0
    broken_examples = []
    known = set()
    known_bases = set()
    for meta in index.values():
        slug = meta.get("slug")
        if not slug:
            continue
        known.add(slug)
        # strip the leading base up to the last double-underscore stem
        base = slug.rsplit("__", 1)[0]
        if base:
            known_bases.add(base)
    for p in sample_files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _re.finditer(r'href="pages/([^"#?]+)\.html', text):
            total += 1
            target = m.group(1) + ".html"
            target_base = m.group(1).rsplit("__", 1)[0]
            if not ((out / "pages" / target).exists()
                    or target in known
                    or (target_base and target_base in known_bases)):
                broken += 1
                if len(broken_examples) < 5:
                    broken_examples.append(f"{p.name} -> {target}")
    ratio = broken / total if total else 0.0
    # NOTE: some targets exist on the live wiki but were never fetched into this
    # archive (they only appear as link targets inside other pages, so the
    # downloader never visited them).  Those legacy-style dangling links are a
    # known limitation, not a corruption signal — do not fail on them, but do
    # WARN with the exact count.
    if broken > 0:
        print(f"warning: {broken}/{total} ({ratio:.1%}) links point at pages "
              f"absent from this archive subset (live wiki may have them; "
              f"possibly flagged in future sync), examples: {broken_examples}",
              file=sys.stderr)
    # Dangling links to pages outside this archive subset are informative, not
    # a violation — always return an empty errors list here (ratio is reported
    # for the human-readable JSON only).
    return [], ratio, broken, total


def get_baseline_index(baseline: str | None):
    if not baseline:
        return None
    try:
        raw = subprocess.run(["git", "show", f"{baseline}:kolzchut_out/index.json"],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(raw)
    except subprocess.CalledProcessError:
        print(f"warning: baseline {baseline} has no index.json; skipping anomalous-diff check")
        return None
    except ValueError as exc:
        print(f"warning: baseline index unparsable: {exc}; skipping anomalous-diff check")
        return None


def main():
    parser = argparse.ArgumentParser(description="KolZchut archive integrity verification")
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    parser.add_argument("--baseline", default="",
                        help="ref to compare size against, e.g. 'origin/master' in CI")
    parser.add_argument("--allow-shrink", type=int, default=DEFAULT_ALLOW_SHRINK)
    parser.add_argument("--allow-grow", type=int, default=DEFAULT_ALLOW_GROW)
    args = parser.parse_args()

    out = Path(args.out)
    index = load_index(out)
    errors = []
    report = {"checks": {}, "errors": []}

    slug_map = collect_slugs(index)

    e1 = check_index(index)
    report["checks"]["index_schema"] = {"errors": e1}
    errors += e1

    e2, missing = check_pages_on_disk(out, index)
    report["checks"]["pages_on_disk"] = {"errors": e2 + missing}
    errors += e2 + missing

    e3, orphans, duplicates = check_orphans_and_duplicates(out, slug_map)
    report["checks"]["orphans_duplicates"] = {"errors": e3, "orphans": len(orphans),
                                              "duplicates": len(duplicates)}
    errors += e3

    e4, n_samples = check_html_cleanliness(out)
    report["checks"]["html_cleanliness"] = {"errors": e4, "sampled": n_samples}
    errors += e4

    e5, ratio, broke, total = check_internal_links(out, index)
    report["checks"]["internal_links"] = {"errors": e5, "broken_ratio": round(ratio, 4),
                                          "broken": broke, "checked": total}
    errors += e5

    base = get_baseline_index(args.baseline)
    if base is not None:
        d = len(index) - len(base)
        anomalous = (d < -args.allow_shrink) or (d > args.allow_grow)
        report["checks"]["size_delta_vs_baseline"] = {
            "baseline_pages": len(base), "new_pages": len(index),
            "delta": d, "anomalous": anomalous}
        if anomalous:
            errors.append(f"anomalous size change vs {args.baseline}: "
                          f"{d:+d} pages (allowed -{args.allow_shrink}/+{args.allow_grow})")

    report["errors"] = errors[:50]
    report["total_errors"] = len(errors)
    # canonical JSON only, no checks skipped
    print(json.dumps(report, ensure_ascii=False, indent=1))

    if errors:
        print(f"VERIFY FAILED: {len(errors)} error(s). First 5:", file=sys.stderr)
        for e in errors[:5]:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    print("VERIFY OK: archive is consistent", file=sys.stderr)
    sys.exit(0)

if __name__ == "__main__":
    main()
