import unittest

from council_v2.bundle import blocking, lint_intake
from council_v2.calibrate import judge, load_decoys, run_calibration
from council_v2.legacy import identical_vectors, legacy_records
from council_v2.seats import MockSeat
from tests.helpers import FACULTY, vec

STRICT = vec(2, 3, 3, 2, 6, 2, 4)
LENIENT = vec(8, 9, 8, 9, 10, 9, 8)  # the 2026 Groq Q2 vector


class Decoys(unittest.TestCase):
    def test_two_decoys_with_neutral_intakes(self):
        ds = load_decoys()
        self.assertEqual(sorted(d.slug for d in ds), ["bruno-maschera", "livia-ornamenti"])
        for d in ds:
            self.assertEqual(blocking(lint_intake(d.intake)), [], d.slug)
            self.assertIn("PASS", d.expected["must_not_be"])
            self.assertTrue((d.repo / "README.md").exists())

    def test_lenient_seat_is_flagged_strict_seat_passes(self):
        seats = [MockSeat("anthropic", scores=STRICT), MockSeat("velocity", scores=LENIENT)]
        rep, results, bundles = run_calibration(seats, faculty_root=FACULTY)
        self.assertEqual(rep.failed, ["velocity"])
        self.assertEqual(rep.seats["anthropic"].status, "passed")
        self.assertTrue(any("raw verdict PASS" in r for r in rep.seats["velocity"].reasons))
        # the same bundle went to both seats, per decoy
        for d, b in bundles.items():
            self.assertTrue(all(results[s][d].log[0].endswith(b.sha256) for s in ("anthropic", "velocity")))

    def test_judged_on_raw_scores_not_capped(self):
        # a decoy repo has zero artifacts: capped, this vector would be vetoed; raw, it is a PASS -> flagged
        rep = judge({"s": {"livia-ornamenti": vec(8, 8, 8, 8, 10, 7, 8)}}, ["livia-ornamenti"])
        self.assertEqual(rep.failed, ["s"])

    def test_high_overall_but_vetoed_is_still_flagged(self):
        rep = judge({"s": {"bruno-maschera": vec(9, 9, 9, 9, 7, 9, 9)}}, ["bruno-maschera"])  # FAIL by veto, overall 8.8
        self.assertEqual(rep.failed, ["s"])
        self.assertTrue(any(">= 7" in r for r in rep.seats["s"].reasons))

    def test_null_on_decoy_means_not_calibrated(self):
        rep, _, _ = run_calibration([MockSeat("longctx", fail="timeout")], faculty_root=FACULTY)
        self.assertEqual(rep.failed, ["longctx"])
        self.assertEqual(rep.status_for("longctx")["status"], "failed")
        self.assertEqual(rep.status_for("nobody")["status"], "not_run")


class NonDiscriminatingSeats(unittest.TestCase):
    def test_groq_q2_identical_vector_detected(self):
        recs = legacy_records(FACULTY, "cohort-q2-2026")
        groups = identical_vectors(recs, 3)
        groq = [g for g in groups if g["seat"] == "groq_velocity"]
        self.assertEqual(groq[0]["vector"], [8, 9, 8, 9, 10, 9, 8])
        self.assertEqual(groq[0]["candidates"], ["adele-maurique", "costanza-notari", "ezio-cardone", "tomaso-riviera"])


if __name__ == "__main__":
    unittest.main()
