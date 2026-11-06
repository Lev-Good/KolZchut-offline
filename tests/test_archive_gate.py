#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
רגרסיה לשער הארכיון (archive gate).

מטרה: ששינוי עתידי בסקריפטים או ב-workflows לא ישבור בשקט את ארבעת מנגנוני
השער, ולא יחזיר בעיות אבטחה שכבר תוקנו. הטסטים מריצים את *הקוד האמיתי* —
או סקריפטים מהפרויקט, או הבלוקים שמוטמעים ב-workflow וחולצים ממנו בזמן הריצה.

מה מכוסה:
  1. שער הסינון — המסנן האמיתי רץ בצד GitHub וחייב להיות no-op, אחרת submission
     שלא סונן נחסם.
  2. שער המחיקות וכשלי הסנכרון — כשל > 0 חוסם; מחיקה של יותר מ-1% מהארכיון חוסמת.
  3. שער השינוי בגודל — shrink/grow חריגים מול ה-baseline מוחזרים כשגיאה.
  4. baseline לא-קריא — שגיאה קשה, ולא דילוג שקט על הבדיקה.
  5. אינווריאנטים של אמון — סקריפטי האימות נלקחים מ-master בלבד; auto-merge
     הוא השער הקובע, יש לו actions:write, הוא content-only, ובדיקת טריות SHA.
  6. חיווט ה-CI — השלב עצמו (סטטוס יציאה אמיתי, "אפס בדיקות אינו ירוק"),
     והחבילה שרצה גם ב-pr-check וגם על master אחרי מיזוג תשתית.
  7. מלאי — אי-אפשר להסיר בדיקה בשקט (EXPECTED_GATE_TESTS + בדיקת ספירה).

הרצה:
  python -m unittest discover -s tests -v
  python tests/test_archive_gate.py -v

לבדיקת מוטציה אפשר להצביע על עץ משוכפל: KOLZCHUT_REPO_ROOT=/path/to/copy
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(os.environ.get("KOLZCHUT_REPO_ROOT", Path(__file__).resolve().parents[1]))
PR_CHECK = REPO / ".github" / "workflows" / "pr-check.yml"
AUTO_MERGE = REPO / ".github" / "workflows" / "auto-merge.yml"
GATE_TESTS = REPO / ".github" / "workflows" / "gate-tests.yml"
PY = sys.executable

# Signature of an unmaterialized Git LFS pointer (kolzchut_out/** is stored in LFS).
LFS_POINTER_MAGIC = b"version https://git-lfs.github.com/spec/v1"

# The contract of this suite: it must stay complete. Without it, "fixing" a red
# gate by deleting the test that caught the problem would be invisible — the
# remaining tests would simply pass. Deliberate additions are fine; they must be
# listed here (and the count below is checked), so a removal cannot hide.
EXPECTED_GATE_TESTS = frozenset({
    # שער הסינון
    "test_unfiltered_submission_is_blocked",
    "test_filtered_submission_passes",
    # שער המחיקות וכשלי הסנכרון
    "test_sync_failures_block_the_merge",
    "test_anomalous_deletions_block_the_merge",
    "test_clean_delta_passes",
    "test_missing_delta_is_not_an_error",
    # שער השינוי בגודל
    "test_large_shrink_is_an_error",
    "test_large_growth_is_an_error",
    "test_change_within_limits_passes_and_is_reported",
    # baseline לא-קריא = שגיאה קשה
    "test_unreadable_baseline_ref_is_a_hard_error",
    "test_missing_baseline_index_file_is_a_hard_error",
    "test_stdout_stays_pure_json_even_when_warnings_are_emitted",
    "test_no_baseline_requested_skips_the_check_without_failing",
    "test_repository_archive_verifies",
    # אינווריאנטים של אמון
    "test_pr_check_never_executes_scripts_from_the_pr",
    "test_every_python_script_invocation_resolves_to_a_base_branch_file",
    "test_pr_check_gate_is_bootstrap_safe",
    "test_auto_merge_can_dispatch_the_release",
    "test_auto_merge_is_triggered_by_the_verify_workflow",
    "test_auto_merge_does_not_poll_the_pr_rollup",
    "test_auto_merge_restricts_to_content_only_prs",
    "test_auto_merge_checks_commit_freshness",
    "test_auto_merge_reports_a_conflict_instead_of_forcing",
    # חיווט ה-CI
    "test_pr_check_runs_the_gate_suite",
    "test_master_push_runs_the_gate_suite",
    "test_a_failing_test_propagates_a_nonzero_exit",
    "test_zero_collected_tests_is_a_failure",
    "test_absent_tests_directory_skips_without_failing",
    # המלאי עצמו
    "test_no_gate_test_was_removed",
    "test_inventory_matches_the_suite_count",
})

HTML_TEMPLATE = ('<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
                 '</head><body><div class="mw-parser-output">{body}</div></body></html>')

# A keyword from the built-in filter list (kolzchut_remove_content.py).
FILTER_KEYWORD = "התאבדות"


def slug_for(i: int) -> str:
    return f"page_{i}__{i:08x}.html"


def write_archive(root: Path, pages: int, *, dirty_page: bool) -> dict:
    """Create a minimal but structurally valid archive directory."""
    pages_dir = root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    index = {}
    for i in range(pages):
        body = f"<p>טקסט רגיל {i}</p>"
        if dirty_page and i == 0:
            body += f"<p>נושא רגיש: {FILTER_KEYWORD} ומניעה.</p>"
        (pages_dir / slug_for(i)).write_text(HTML_TEMPLATE.format(body=body), encoding="utf-8")
        index[f"דף {i}"] = {"slug": slug_for(i), "status": "ok"}
    (root / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    return index


def write_delta(root: Path, *, deleted: int = 0, failed: int = 0) -> None:
    deleted_pages = [f"דף {i}" for i in range(deleted)]
    (root / "delta.json").write_text(json.dumps({
        "since": "2026-01-01T00:00:00Z",
        "fetched_at": "2026-01-01T00:00:00Z",
        "changed": [],
        "deleted": deleted_pages,
        "counts": {"changed": 0, "failed": failed, "deleted": deleted},
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def run_python(source: str, cwd: Path, args=()) -> subprocess.CompletedProcess:
    """Run a Python block as a real process (as CI does) and return the result."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(source)
        path = fh.name
    try:
        return subprocess.run([PY, path, *args], cwd=str(cwd),
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    finally:
        Path(path).unlink(missing_ok=True)


def extract_python_block(workflow: Path, step_prefix: str) -> str:
    """Pull the embedded `python - <<'PY' … PY` body out of a workflow step.

    Extraction (rather than a copy of the logic) is deliberate: these tests then
    run exactly what CI runs, and a refactor that removes the guard fails here
    instead of quietly dropping the check.
    """
    text = workflow.read_text(encoding="utf-8")
    anchor = text.find(f"name: {step_prefix}")
    if anchor < 0:
        raise AssertionError(f"step {step_prefix!r} not found in {workflow.name}")
    start = text.find("<<'PY'\n", anchor)
    if start < 0:
        raise AssertionError(f"step {step_prefix!r} has no embedded python block")
    body_start = start + len("<<'PY'\n")
    end = re.search(r"\n\s*PY\s*(\n|$)", text[body_start:])
    if not end:
        raise AssertionError(f"step {step_prefix!r} has an unterminated python block")
    return textwrap.dedent(text[body_start:body_start + end.start()])


def extract_run_block(workflow: Path, step_prefix: str) -> str:
    """Pull the whole shell script of a workflow step out of the YAML.

    Same idea as extract_python_block: the tests execute what CI executes, so
    deleting or weakening the step fails here instead of passing unnoticed.
    """
    text = workflow.read_text(encoding="utf-8")
    anchor = text.find(f"name: {step_prefix}")
    if anchor < 0:
        raise AssertionError(f"step {step_prefix!r} not found in {workflow.name}")
    # Bound the search to this step: the run block belongs to it, not to the
    # neighbour step (a naive search silently returns the wrong script).
    next_step = re.search(r"\n      - name:", text[anchor:])
    step_end = anchor + (next_step.start() if next_step else len(text) - anchor)
    start = text.find("\n        run: |\n", anchor, step_end)
    if start < 0:
        raise AssertionError(f"step {step_prefix!r} has no literal run block")
    start += len("\n        run: |\n")
    chunk = text[start:step_end]
    return textwrap.dedent(chunk)


class ArchiveFixture(unittest.TestCase):
    """Shared setup: a temp dir with a synthetic archive tree."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="kolzchut-gate-")
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def ci_filter_copy(self, *, submitted_dirty: bool, submitter_filtered: bool):
        """Reproduce the CI layout: pr-archive/kolzchut_out + kolzchut_out."""
        submitted = self.tmp / "pr-archive" / "kolzchut_out"
        write_archive(submitted, 2, dirty_page=submitted_dirty)
        filter_script = REPO / "kolzchut_remove_content.py"
        if submitter_filtered:
            r = subprocess.run([PY, str(filter_script), "--default-charedi-list"],
                               cwd=str(self.tmp / "pr-archive"), capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 0, r.stderr)
        ci_copy = self.tmp / "kolzchut_out"
        (self.tmp / "kolzchut_out").parent.mkdir(parents=True, exist_ok=True)
        _copytree(submitted, ci_copy)
        return ci_copy, filter_script


def _copytree(src: Path, dst: Path) -> None:
    import shutil
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


class ContentFilterGateTests(ArchiveFixture):
    """שער 1: המסנן האמיתי רץ ב-CI וחייב להיות no-op."""

    def _run_gate(self, *, submitter_filtered: bool):
        ci_copy, filter_script = self.ci_filter_copy(
            submitted_dirty=True, submitter_filtered=submitter_filtered)
        r = subprocess.run([PY, str(filter_script), "--default-charedi-list"],
                           cwd=str(self.tmp), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stderr)
        block = extract_python_block(PR_CHECK, "Enforce the content filter")
        return run_python(block, self.tmp)

    def test_unfiltered_submission_is_blocked(self):
        r = self._run_gate(submitter_filtered=False)
        self.assertNotEqual(r.returncode, 0,
                            f"unfiltered archive must be blocked, stdout={r.stdout!r}")
        self.assertIn("CONTENT FILTER NOT APPLIED", r.stderr)

    def test_filtered_submission_passes(self):
        r = self._run_gate(submitter_filtered=True)
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout!r} stderr={r.stderr!r}")
        self.assertIn("no-op", r.stdout)


class DeletionGateTests(ArchiveFixture):
    """שער 2: כשלי סנכרון ומחיקות חריגות."""

    def _run_gate(self, *, deleted: int, failed: int, pages: int = 100):
        archive = self.tmp / "kolzchut_out"
        write_archive(archive, pages, dirty_page=False)
        write_delta(archive, deleted=deleted, failed=failed)
        block = extract_python_block(PR_CHECK, "Verify deletions and sync failures")
        return run_python(block, self.tmp)

    def test_sync_failures_block_the_merge(self):
        r = self._run_gate(deleted=0, failed=3)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SYNC ERRORS REPORTED", r.stderr)

    def test_anomalous_deletions_block_the_merge(self):
        # 5 of 100 pages = 5% > the 1% ceiling
        r = self._run_gate(deleted=5, failed=0, pages=100)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ANOMALOUS DELETION", r.stderr)

    def test_clean_delta_passes(self):
        r = self._run_gate(deleted=0, failed=0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("deletion check ok", r.stdout)

    def test_missing_delta_is_not_an_error(self):
        archive = self.tmp / "kolzchut_out"
        write_archive(archive, 3, dirty_page=False)
        block = extract_python_block(PR_CHECK, "Verify deletions and sync failures")
        r = run_python(block, self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)


class SizeGateTests(ArchiveFixture):
    """שער 3: שינוי חריג בגודל מול ה-baseline."""

    def _verify(self, *, pages: int, baseline_pages: int, allow_shrink=200,
                allow_grow=2000):
        archive = self.tmp / "archive"
        write_archive(archive, pages, dirty_page=False)
        baseline = self.tmp / "baseline.json"
        baseline.write_text(json.dumps(
            {f"base {i}": {"slug": slug_for(i), "status": "ok"}
             for i in range(baseline_pages)}, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [PY, str(REPO / "kolzchut_verify.py"), "--out", str(archive),
             "--baseline-index", str(baseline),
             "--allow-shrink", str(allow_shrink), "--allow-grow", str(allow_grow)],
            cwd=str(self.tmp), capture_output=True, text=True,
            encoding="utf-8", errors="replace")

    def test_large_shrink_is_an_error(self):
        r = self._verify(pages=1, baseline_pages=5, allow_shrink=1, allow_grow=1)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("anomalous size change", r.stderr)

    def test_large_growth_is_an_error(self):
        r = self._verify(pages=5, baseline_pages=1, allow_shrink=1, allow_grow=1)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("anomalous size change", r.stderr)

    def test_change_within_limits_passes_and_is_reported(self):
        r = self._verify(pages=4, baseline_pages=2, allow_shrink=2, allow_grow=2)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        report = json.loads(r.stdout)
        self.assertIn("size_delta_vs_baseline", report["checks"])
        self.assertEqual(report["checks"]["size_delta_vs_baseline"]["delta"], 2)
        self.assertFalse(report["checks"]["size_delta_vs_baseline"]["anomalous"])


class BaselineStrictnessTests(ArchiveFixture):
    """שער 4: baseline מבוקש שאינו קריא הוא שגיאה, לא דילוג שקט."""

    def _verify(self, *args):
        archive = self.tmp / "archive"
        write_archive(archive, 2, dirty_page=False)
        return subprocess.run(
            [PY, str(REPO / "kolzchut_verify.py"), "--out", str(archive), *args],
            cwd=str(self.tmp), capture_output=True, text=True,
            encoding="utf-8", errors="replace")

    def test_unreadable_baseline_ref_is_a_hard_error(self):
        r = self._verify("--baseline", "no-such-ref-xyz")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("could not be read", r.stderr)
        report = json.loads(r.stdout)
        self.assertIn("size_delta_vs_baseline", report["checks"])
        self.assertTrue(report["checks"]["size_delta_vs_baseline"]["errors"])

    def test_missing_baseline_index_file_is_a_hard_error(self):
        r = self._verify("--baseline-index", str(self.tmp / "missing.json"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_stdout_stays_pure_json_even_when_warnings_are_emitted(self):
        """אזהרות חייבות ללכת ל-stderr, אחרת כל צרכן JSON נשבר."""
        r = self._verify("--baseline", "no-such-ref-xyz")
        json.loads(r.stdout)          # raises if a warning leaked into stdout
        self.assertNotIn("warning:", r.stdout)

    def test_no_baseline_requested_skips_the_check_without_failing(self):
        r = self._verify()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        report = json.loads(r.stdout)
        self.assertNotIn("size_delta_vs_baseline", report["checks"])

    def test_repository_archive_verifies(self):
        """הארכיון שבריפו חייב לעבור — אחרת כל PR ייחסם."""
        index = REPO / "kolzchut_out" / "index.json"
        if not index.exists():
            self.skipTest("kolzchut_out/index.json not present")
        if index.read_bytes()[:len(LFS_POINTER_MAGIC)] == LFS_POINTER_MAGIC:
            # An LFS pointer is not content: there is nothing to verify here.
            # This is why pr-check runs the suite *after* staging the submitted
            # archive — there the file is real and this test does its job.
            self.skipTest("kolzchut_out/index.json is an unmaterialized Git LFS "
                          "pointer — run `git lfs pull` to include this check")
        r = subprocess.run([PY, str(REPO / "kolzchut_verify.py")], cwd=str(REPO),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        self.assertEqual(r.returncode, 0, r.stderr)


class TrustBoundaryTests(unittest.TestCase):
    """שער 5: אינווריאנטים שמונעים חזרה של פרצות האמון והדדלוק."""

    def setUp(self):
        self.pr_check = PR_CHECK.read_text(encoding="utf-8")
        self.auto_merge = AUTO_MERGE.read_text(encoding="utf-8")

    def _steps(self, workflow_text: str) -> list:
        return re.findall(r"run: \|\n((?:[ \t]+.*\n|\n)*)", workflow_text)

    def test_pr_check_never_executes_scripts_from_the_pr(self):
        """הסקריפטים חייבים להילקח מ-checkout הבסיס, לא מ-pr-archive/."""
        # Only a script *argument* counts (the test suite runs from pr-archive/tests).
        offenders = re.findall(r"python\s+\S*pr-archive/\S+\.py", self.pr_check)
        self.assertEqual(offenders, [],
                         "pr-check must not run verification scripts from the PR: "
                         f"{offenders}")

    def test_every_python_script_invocation_resolves_to_a_base_branch_file(self):
        for m in re.finditer(r"python\s+([A-Za-z0-9_./-]+\.py)", self.pr_check):
            script = m.group(1)
            self.assertFalse(script.startswith("pr-archive/"),
                             f"script from the PR would be executed: {script}")
            self.assertTrue((REPO / script).exists(),
                            f"pr-check references a script that is not in the base "
                            f"branch: {script}")

    def test_pr_check_gate_is_bootstrap_safe(self):
        """אין להשתמש בדגלים שאינם קיימים ב-master, אחרת כל PR נחסם."""
        self.assertNotIn("--require-baseline", self.pr_check)
        self.assertNotIn("--baseline-index", self.pr_check)
        self.assertIn("pip install requests beautifulsoup4", self.pr_check)
        self.assertNotIn("pip install -r", self.pr_check)

    def test_auto_merge_can_dispatch_the_release(self):
        self.assertRegex(self.auto_merge, r"permissions:\s*\n(?:.*\n)*?\s+actions: write")

    def test_auto_merge_is_triggered_by_the_verify_workflow(self):
        verify_name = re.search(r"^name: (.+)$", self.pr_check, re.M).group(1).strip()
        self.assertIn("workflow_run", self.auto_merge)
        self.assertIn(f'"{verify_name}"', self.auto_merge)

    def _run_blocks(self, workflow_text: str) -> str:
        """כל בלוקי ה-`run:` בלבד — הקומנטריים שמסבירים אינם קוד."""
        return "\n".join(re.findall(r"run: \|\n((?:[ \t]+.*\n|\s*\n)*)", workflow_text))

    def test_auto_merge_does_not_poll_the_pr_rollup(self):
        """ה-job's run's own check runs appear in the rollup — polling deadlocks."""
        self.assertNotIn("statusCheckRollup", self._run_blocks(self.auto_merge))

    def test_auto_merge_restricts_to_content_only_prs(self):
        self.assertIn("^(kolzchut_out/|docs/)", self.auto_merge)

    def test_auto_merge_checks_commit_freshness(self):
        self.assertIn("headRefOid", self.auto_merge)
        self.assertIn("head_sha", self.auto_merge)

    def test_auto_merge_reports_a_conflict_instead_of_forcing(self):
        self.assertIn("DIRTY", self.auto_merge)
        self.assertIn("--squash", self.auto_merge)

    def test_pr_check_runs_the_gate_suite(self):
        """החבילה חייבת לרוץ ב-CI, ואסור שספירת אפס טסטים תיראה כמו הצלחה."""
        self.assertIn("unittest discover -s tests", self.pr_check)
        self.assertIn("Ran [1-9][0-9]* tests?", self.pr_check)

    def test_master_push_runs_the_gate_suite(self):
        """שינויי תשתית (שה-auto-merge מסרב להם) נבדקים על master אחרי המיזוג."""
        text = GATE_TESTS.read_text(encoding="utf-8")
        self.assertRegex(text, r"push:\s*\n(?:.*\n)*?\s+branches: \[master\]")
        self.assertIn("unittest discover -s tests", text)
        self.assertIn("Ran [1-9][0-9]* tests?", text)


def _iter_test_names(suite):
    """Expand a (possibly nested) suite into individual test method names."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_test_names(item)
        else:
            yield item._testMethodName


class CiStepTests(ArchiveFixture):
    """שער 6: השלב עצמו — סטטוס יציאה אמיתי, ולא "ירוק" מדומה."""

    STEP = "Gate regression suite"

    def setUp(self):
        if shutil.which("bash") is None:
            self.skipTest("bash not available to execute the workflow step")
        super().setUp()

    def run_step(self, cwd: Path):
        script = self.tmp / "gate-step.sh"
        script.write_text(extract_run_block(PR_CHECK, self.STEP),
                          encoding="utf-8", newline="\n")
        # Deliberately *no* -e here: the step must carry its own exit-status
        # handling instead of relying on the runner's implicit `bash -e`.
        return subprocess.run(["bash", str(script)], cwd=str(cwd),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")

    def test_a_failing_test_propagates_a_nonzero_exit(self):
        """בלי זה `tee` בלע את הכשל וה-שער היה ירוק בכל מצב."""
        tests_dir = self.tmp / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_synthetic.py").write_text(
            "import unittest\n"
            "\n"
            "\n"
            "class Synthetic(unittest.TestCase):\n"
            "    def test_bad(self):\n"
            "        self.fail('synthetic failure')\n", encoding="utf-8")
        r = self.run_step(self.tmp)
        blob = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, f"failure swallowed by tee: {blob}")
        self.assertIn("FAILED", blob)

    def test_zero_collected_tests_is_a_failure(self):
        (self.tmp / "tests").mkdir()
        r = self.run_step(self.tmp)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("collected zero tests", r.stdout + r.stderr)

    def test_absent_tests_directory_skips_without_failing(self):
        """Bootstrap: master שלפני החבילה לא אמור לחסום כל PR."""
        r = self.run_step(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("skipping", r.stdout)


class SuiteInventoryTests(unittest.TestCase):
    """שער 6: אי אפשר "לתקן" שער אדום ע"י מחיקת הבדיקה שתפסה אותו.

    EXPECTED_GATE_TESTS הוא החוזה. כשמוסיפים בדיקה בכוונה — מוסיפים את שמה
    לשם. מחיקה/שינוי-שם בלי לעדכן את המלאי יכשלו בשתי בדיקות: החסר לפי שם,
    והספירה הכוללת. כך גם מחיקה של בדיקה *וגם* הסרת שמה מהמלאי נתפסת.
    """

    def discovered(self):
        module = sys.modules[__name__]
        suite = unittest.TestLoader().loadTestsFromModule(module)
        return list(_iter_test_names(suite))

    def test_no_gate_test_was_removed(self):
        missing = sorted(EXPECTED_GATE_TESTS - set(self.discovered()))
        self.assertEqual(
            missing, [],
            "gate test(s) deleted or renamed away — the guard they enforced is "
            f"now unverified: {missing}")

    def test_inventory_matches_the_suite_count(self):
        names = self.discovered()
        self.assertEqual(
            len(names), len(EXPECTED_GATE_TESTS),
            "the suite and EXPECTED_GATE_TESTS disagree on the number of tests "
            f"(found {len(names)}, inventory {len(EXPECTED_GATE_TESTS)}) — update "
            "the inventory so the guard against silent removals stays accurate")


if __name__ == "__main__":
    unittest.main(verbosity=2)
