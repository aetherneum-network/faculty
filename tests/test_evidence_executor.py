import os
import unittest

from council_v2 import scoring
from council_v2.evidence import _redact_identity, classify, scan_repo
from council_v2.executor import ContainmentError, resolve_command, run_scenarios
from tests.helpers import FIXTURES, REPOS_ROOT, vec

TINY = FIXTURES / "tiny_repo"
EMPTY = FIXTURES / "empty_repo"


class Evidence(unittest.TestCase):
    def test_profile_only_repo_has_zero_artifacts_and_caps(self):
        m = scan_repo(EMPTY)
        self.assertEqual(m["artifact_count"], 0)
        self.assertFalse(m["has_code"] or m["has_tests"] or m["has_ci"] or m["has_scenarios"])
        s = scoring.score_seat(vec(9, 9, 9, 9, 10, 9, 9), scoring.evidence_caps(m))
        self.assertEqual(s.scores_effective["body_of_work_depth"], 3)
        self.assertEqual(s.verdict, "FAIL")

    def test_fixture_counts(self):
        m = scan_repo(TINY)
        self.assertTrue(m["has_code"] and m["has_tests"] and m["has_ci"] and m["has_scenarios"])
        self.assertEqual(m["counts"]["scenario"], 7)
        self.assertEqual(scoring.evidence_caps(m), [])
        self.assertEqual(m["git"], {"is_git_repo": False})  # a nested dir does not inherit faculty's git facts

    def test_classify(self):
        self.assertEqual(classify("README.md"), None)
        self.assertEqual(classify("avatar.jpg"), None)
        self.assertEqual(classify("LICENSE"), None)
        self.assertEqual(classify("src/x.sol"), "code")
        self.assertEqual(classify("tests/test_x.py"), "test")
        self.assertEqual(classify("web/x.spec.ts"), "test")
        self.assertEqual(classify(".github/workflows/ci.yml"), "ci")

    def test_personal_addresses_are_redacted(self):
        self.assertEqual(_redact_identity("Lucia Solari <lucia.solari@aetherneum.com>"), "Lucia Solari <lucia.solari@aetherneum.com>")
        self.assertEqual(_redact_identity("Some Operator <someone@example.org>"), "[non-alumnus identity, redacted]")
        self.assertEqual(_redact_identity("Aetherneum <aetherneum@aetherneum.com>"), "[non-alumnus identity, redacted]")

    @unittest.skipUnless((REPOS_ROOT / "ezio-cardone" / ".git").exists(), "sibling clone not present")
    def test_real_alumnus_repo_at_main_has_zero_artifacts(self):
        m = scan_repo(REPOS_ROOT / "ezio-cardone", ref="main")
        self.assertEqual(m["artifact_count"], 0)
        self.assertEqual(sorted(f["path"] for f in m["files"]), ["LICENSE", "README.md", "avatar.jpg"])


class Executor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["FAKE_PROVIDER_API_KEY"] = "must-not-leak"
        try:
            cls.res = run_scenarios(TINY)
        finally:
            os.environ.pop("FAKE_PROVIDER_API_KEY", None)
        cls.by = {r.scenario_id: r for r in cls.res.results}

    def test_counts(self):
        self.assertEqual(self.res.scenarios_found, 7)
        self.assertEqual((self.res.passed, self.res.failed, self.res.timeouts, self.res.errors), (3, 1, 1, 2))

    def test_pass_fail_timeout(self):
        self.assertEqual(self.by["s01_pass"].status, "pass")  # also proves secrets were stripped from env
        self.assertEqual(self.by["s02_fail"].status, "fail")
        self.assertEqual(self.by["s02_fail"].exit_code, 1)
        self.assertEqual(self.by["s03_json"].status, "pass")
        self.assertEqual(self.by["s04_timeout"].status, "timeout")
        self.assertEqual(self.by["s07_unittest"].status, "pass")

    def test_containment(self):
        self.assertEqual(self.by["s05_escape"].status, "error")
        self.assertIn("inside the repository", self.by["s05_escape"].error)
        self.assertEqual(self.by["s06_foreign_program"].status, "error")
        self.assertIn("outside the repository", self.by["s06_foreign_program"].error)
        with self.assertRaises(ContainmentError):
            resolve_command(TINY, TINY / "scenarios" / "s05_escape")

    def test_commands_recorded_without_absolute_paths(self):
        cmd = self.by["s01_pass"].command
        self.assertEqual(cmd, ["python", "run.py"])

    def test_missing_repo(self):
        with self.assertRaises(ContainmentError):
            run_scenarios(FIXTURES / "does-not-exist")


if __name__ == "__main__":
    unittest.main()
