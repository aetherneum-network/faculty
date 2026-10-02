import json
import tempfile
import unittest
from pathlib import Path

from council_v2 import scoring
from council_v2.bundle import build_bundle
from council_v2.record import build_decision_record, build_seat_record, write_signed, RecordExists
from council_v2.scoring import QuorumRule, SeatOutcome, decide_council, score_seat
from council_v2.seats import MockSeat
from council_v2.signing import Ed25519Signer, verify_record
from tests.helpers import FACULTY, FIXTURES, vec

SEATS = ("anthropic", "reasoning", "longctx", "velocity")
RULE = QuorumRule(voting_seats=SEATS)
GOOD = score_seat(vec(9, 9, 9, 9, 10, 8, 9))


def ok(sid, sc=GOOD, calibrated=True):
    return SeatOutcome(sid, "ok", sc, calibrated=calibrated)


class Quorum(unittest.TestCase):
    def test_four_pass(self):
        d = decide_council([ok(s) for s in SEATS], RULE)
        self.assertEqual((d.outcome, d.tally, d.reduced_quorum), ("PASS", "4/4", False))

    def test_one_null_seat_is_absent_not_pass(self):
        d = decide_council([ok("anthropic"), ok("reasoning"), ok("longctx"), SeatOutcome("velocity", "null", error="timeout")], RULE)
        self.assertEqual(d.outcome, "PASS")
        self.assertEqual(d.tally, "3/3")
        self.assertTrue(d.reduced_quorum)
        self.assertEqual(d.null_seats, ["velocity"])
        self.assertTrue(any("reduced quorum" in r for r in d.reasons))

    def test_two_null_seats_no_quorum(self):
        d = decide_council([ok("anthropic"), ok("reasoning"), SeatOutcome("longctx", "null"), SeatOutcome("velocity", "null")], RULE)
        self.assertEqual(d.outcome, "NO_QUORUM")

    def test_missing_record_counts_as_absent(self):
        d = decide_council([ok("anthropic"), ok("reasoning"), ok("longctx")], RULE)
        self.assertEqual(d.missing_seats, ["velocity"])
        self.assertEqual(d.tally, "3/3")
        self.assertTrue(d.reduced_quorum)

    def test_null_seat_cannot_rescue_a_veto(self):
        veto = score_seat(vec(4, 9, 9, 9, 10, 8, 9))
        d = decide_council([ok("anthropic", veto), ok("reasoning"), ok("longctx"), SeatOutcome("velocity", "null")], RULE)
        self.assertEqual(d.outcome, "VETO")

    def test_most_restrictive_wins(self):
        pwr = score_seat(vec(6, 9, 9, 9, 10, 8, 9))
        d = decide_council([ok("anthropic", pwr), ok("reasoning"), ok("longctx"), ok("velocity")], RULE)
        self.assertEqual(d.outcome, "REVISIONS_REQUIRED")
        fail = score_seat(vec(6, 6, 6, 6, 9, 6, 6))
        d = decide_council([ok("anthropic", fail), ok("reasoning", pwr), ok("longctx"), ok("velocity")], RULE)
        self.assertEqual(d.outcome, "FAIL")

    def test_uncalibrated_seat_is_excluded(self):
        d = decide_council([ok("anthropic"), ok("reasoning"), ok("longctx"), ok("velocity", calibrated=False)], RULE)
        self.assertEqual(d.excluded_uncalibrated, ["velocity"])
        self.assertEqual(d.tally, "3/3")
        d = decide_council([ok("anthropic"), ok("reasoning"), ok("longctx", calibrated=False), ok("velocity", calibrated=False)], RULE)
        self.assertEqual(d.outcome, "NO_QUORUM")


class NullSeatRecords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = build_bundle("tiny-repo", faculty_root=FACULTY, profile_path=FIXTURES / "tiny_repo" / "README.md",
                                  evidence_manifest={"artifact_count": 0, "artifacts": [], "files": []})

    def test_failing_seat_returns_null_result_not_exception(self):
        r = MockSeat("velocity", fail="provider timeout").score(self.bundle)
        self.assertEqual(r.status, "null")
        self.assertIsNone(r.output)
        self.assertEqual(r.error["type"], "RuntimeError")
        self.assertTrue(any("ERROR" in line for line in r.log))

    def test_null_record_is_written_signed_with_error_and_log(self):
        signer = Ed25519Signer.generate()
        session = {"session_id": "t", "dry_run": True, "mock": True}
        res = MockSeat("velocity", fail="HTTP 429").score(self.bundle)
        rec = build_seat_record(session, {"role": "Velocity", "voting": True}, res, self.bundle, candidate={"slug": "tiny-repo"})
        with tempfile.TemporaryDirectory() as td:
            p = write_signed(rec, Path(td) / "tiny-repo__velocity.json", signer)
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "null")
            self.assertIsNone(data["scores_raw"])
            self.assertIsNone(data["scoring"])
            self.assertIn("HTTP 429", data["error"]["message"])
            self.assertTrue(data["log"])
            self.assertEqual(data["bundle_sha256"], self.bundle.sha256)
            self.assertTrue(verify_record(data, signer.public_key).ok)
            with self.assertRaises(RecordExists):
                write_signed(rec, p, signer)  # append-only

    def test_decision_recomputed_from_records(self):
        session = {"session_id": "t", "dry_run": True, "mock": True}
        recs = []
        for sid in SEATS:
            seat = MockSeat(sid, fail="down" if sid == "velocity" else None, scores=vec(9, 9, 9, 9, 10, 8, 9))
            recs.append(build_seat_record(session, {"role": sid, "voting": True}, seat.score(self.bundle), self.bundle,
                                          candidate={"slug": "tiny-repo"}, caps=[]))
        dec = build_decision_record(session, {"slug": "tiny-repo"}, recs, RULE, bundle_sha256=self.bundle.sha256)
        self.assertEqual(dec["decision"]["outcome"], scoring.OUTCOME_PASS)
        self.assertEqual(dec["decision"]["tally"], "3/3")
        self.assertTrue(dec["decision"]["reduced_quorum"])
        self.assertIn("tiny-repo__velocity.json", dec["seat_files"])


if __name__ == "__main__":
    unittest.main()
