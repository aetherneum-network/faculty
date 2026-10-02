"""End-to-end dry run: lint -> bundle -> calibration -> seats -> scoring -> signed records.  Offline."""

import json
import tempfile
import unittest
from pathlib import Path

from council_v2 import run_council_v2 as rc
from council_v2.bundle import SteeringError
from council_v2.record import load_records
from council_v2.registry import load_council
from council_v2.signing import Ed25519Signer
from tests.helpers import FACULTY, FIXTURES

COUNCIL = load_council(FACULTY / "council" / "council.json")
DECOY = FACULTY / "council_v2" / "decoys" / "livia-ornamenti"


class DryRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.signer = Ed25519Signer.generate("test")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **kw):
        args = dict(repos_root=FACULTY.parent, out_root=self.out, signer=self.signer, dry_run=True, mock=True,
                    intake=None, profile=FIXTURES / "tiny_repo" / "README.md", repo=FIXTURES / "tiny_repo")
        args.update(kw)
        seats = args.pop("seats", None) or rc.build_mock_seats(COUNCIL)
        return rc.run("tiny-repo", seats=seats, **args)

    def test_full_pipeline_writes_verifiable_records(self):
        s = self._run()
        out = Path(s["out"])
        names = sorted(p.name for p in out.glob("*.json"))
        self.assertEqual(names, ["tiny-repo__DECISION.json", "tiny-repo__anthropic.json", "tiny-repo__executor.json",
                                 "tiny-repo__longctx.json", "tiny-repo__reasoning.json", "tiny-repo__velocity.json"])
        recs, rejected = load_records([out], self.signer.public_key)
        self.assertEqual(rejected, [])
        self.assertEqual(len(recs), 6 + 1 + 8)  # + calibration summary + 2 decoys x 4 seats
        seat = json.loads((out / "tiny-repo__anthropic.json").read_text(encoding="utf-8"))
        for k in ("model_from_response", "request_id", "response_id", "raw_response", "params", "bundle_sha256",
                  "faculty_commit", "prompt_sha256", "started_at", "finished_at", "signature"):
            self.assertIn(k, seat)
        self.assertEqual(seat["bundle_sha256"], s["bundle_sha256"])
        self.assertEqual(seat["calibration"]["status"], "passed")
        ex = json.loads((out / "tiny-repo__executor.json").read_text(encoding="utf-8"))
        self.assertEqual((ex["result"]["passed"], ex["result"]["failed"]), (3, 1))
        # the fixture has artifacts and scenarios that start, so no evidence cap; the default mock vector
        # 8·8·8·8·10·7·8 meets every threshold: the four seats PASS.  Until 2026-09-30 the outcome was PASS;
        # rule EX-1 (Rector decision D19) makes it a VETO, because 4 of the 7 declared scenarios do not pass.
        self.assertEqual(s["caps"], [])
        self.assertEqual(s["decision"]["pass_count"], 4)
        self.assertEqual(s["decision"]["outcome"], "VETO")
        self.assertEqual(s["decision"]["vetoes"], {"executor": ["EX-1.a: 4 of 7 declared scenarios not passed"]})
        self.assertEqual(seat["executor"]["counts"], {"scenarios_found": 7, "passed": 3, "failed": 1, "errors": 2, "timeouts": 1})

    def test_zero_artifacts_candidate_is_vetoed_by_cap(self):
        s = self._run(profile=DECOY / "profile.md", repo=FIXTURES / "empty_repo")
        self.assertEqual(s["decision"]["outcome"], "VETO")
        self.assertEqual(s["caps"][0]["cap"], 3)

    def test_null_seat_and_uncalibrated_seat(self):
        seats = rc.build_mock_seats(COUNCIL, fail_seat="velocity", lenient_seat="reasoning")
        # quorum is the subject here: the executor is left out (dry run), otherwise rule EX-1 vetoes this fixture first
        s = self._run(seats=seats, run_executor=False)
        d = s["decision"]
        self.assertEqual(d["null_seats"], ["velocity"])
        self.assertEqual(d["excluded_uncalibrated"], ["reasoning"])
        self.assertEqual(d["outcome"], "NO_QUORUM")
        null = json.loads((Path(s["out"]) / "tiny-repo__velocity.json").read_text(encoding="utf-8"))
        self.assertEqual(null["status"], "null")
        self.assertTrue(null["log"])

    def test_steering_intake_blocks_and_is_recorded(self):
        with self.assertRaises(SteeringError):
            self._run(intake=FIXTURES / "steering" / "intake-with-steering.md")
        blocked = list(self.out.rglob("*__LINT_BLOCKED.json"))
        self.assertEqual(len(blocked), 1)
        recs, rejected = load_records(blocked, self.signer.public_key)
        self.assertEqual(recs[0]["outcome"], "BLOCKED_BY_LINT")
        self.assertEqual(list(self.out.rglob("*__anthropic.json")), [])  # no seat was called

    def test_decoys_never_reach_the_registry(self):
        from council_v2 import registry

        s = self._run()
        rows, rejected = registry.build([s["out"]], self.signer.public_key, COUNCIL, include_mock=True)
        self.assertEqual(rejected, [])
        self.assertEqual([r.slug for r in rows], ["tiny-repo"])

    def test_cli_refuses_live_without_approval(self):
        self.assertEqual(rc.main(["--slug", "costanza-notari", "--live"]), 2)
        self.assertEqual(rc.main(["--slug", "costanza-notari", "--live", "--mock"]), 2)


if __name__ == "__main__":
    unittest.main()
