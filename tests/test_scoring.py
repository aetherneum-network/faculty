import unittest
from fractions import Fraction

from council_v2 import scoring
from council_v2.scoring import (FAIL, PASS, PASS_WITH_REVISIONS, Cap, ScoreError, evidence_caps, score_seat,
                                weighted_overall)
from tests.helpers import legacy, vec


class WeightsAndOverall(unittest.TestCase):
    def test_weights_exactly_as_rubric(self):
        w = {c.key: c.weight for c in scoring.CRITERIA}
        self.assertEqual(w, {
            "body_of_work_depth": Fraction(3, 2), "specialty_uniqueness": Fraction(3, 2),
            "voice_personality_clarity": 1, "faithful_distillation": 1, "synthetic_transparency": 1,
            "placement_fit": 1, "continuity_with_class": Fraction(1, 2),
        })
        self.assertEqual(scoring.SUM_WEIGHTS, Fraction(15, 2))

    def test_thresholds_and_vetoes_exactly_as_rubric(self):
        t = {c.key: (c.threshold, c.veto_below) for c in scoring.CRITERIA}
        self.assertEqual(t, {
            "body_of_work_depth": (7, 5), "specialty_uniqueness": (7, 5), "voice_personality_clarity": (7, None),
            "faithful_distillation": (7, None), "synthetic_transparency": (9, 9), "placement_fit": (6, None),
            "continuity_with_class": (6, None),
        })

    def test_all_tens_is_ten(self):
        self.assertEqual(weighted_overall(vec(10, 10, 10, 10, 10, 10, 10)), 10)

    def test_weighting_matters(self):
        # a point on body of work (1.5) is worth three points on continuity (0.5)
        a = weighted_overall(vec(8, 8, 8, 8, 10, 8, 8))
        b = weighted_overall(vec(9, 8, 8, 8, 10, 8, 5))
        self.assertEqual(a, b)

    def test_costanza_q2_recomputed_values_match_review(self):
        # docs/2026-09-30_Revisione_Aetherneum.html §3 table: 9,33 · 9,67 · 9,53 · 8,73
        expected = {"anthropic_chair": 9.33, "cerebras_reasoning": 9.67, "moonshot_longctx": 9.53, "groq_velocity": 8.73}
        for seat, want in expected.items():
            d = legacy("cohort-q2-2026", "costanza-notari", seat)
            self.assertEqual(score_seat(d["criterion_scores"]).overall, want, seat)

    def test_model_written_overall_is_not_used(self):
        d = legacy("cohort-q2-2026", "costanza-notari", "anthropic_chair")
        self.assertEqual(d["overall_score"], 9.36)
        self.assertEqual(score_seat(d["criterion_scores"]).overall, 9.33)


class Verdicts(unittest.TestCase):
    def test_pass(self):
        s = score_seat(vec(9, 9, 9, 9, 10, 8, 9))
        self.assertEqual(s.verdict, PASS)
        self.assertEqual(s.vetoes, [])

    def test_veto_synthetic_transparency_below_9(self):
        s = score_seat(vec(10, 10, 10, 10, 8, 10, 10))
        self.assertEqual(s.verdict, FAIL)
        self.assertIn("synthetic_transparency 8 < 9", s.vetoes)
        self.assertGreater(s.overall, 9)  # overall is high, the veto still wins

    def test_veto_body_of_work_below_5(self):
        s = score_seat(vec(4, 10, 10, 10, 10, 10, 10))
        self.assertEqual(s.verdict, FAIL)
        self.assertEqual(s.vetoes, ["body_of_work_depth 4 < 5"])

    def test_veto_uniqueness_below_5(self):
        s = score_seat(vec(10, 4, 10, 10, 10, 10, 10))
        self.assertEqual(s.verdict, FAIL)
        self.assertEqual(s.vetoes, ["specialty_uniqueness 4 < 5"])

    def test_floor_below_5_fails_without_veto(self):
        s = score_seat(vec(9, 9, 9, 9, 10, 4, 9))
        self.assertEqual(s.vetoes, [])
        self.assertEqual(s.verdict, FAIL)
        self.assertIn("placement_fit", s.below_floor)

    def test_overall_below_7_fails(self):
        s = score_seat(vec(6, 6, 6, 6, 9, 6, 6))
        self.assertEqual(s.verdict, FAIL)

    def test_below_table_threshold_is_pass_with_revisions(self):
        s = score_seat(vec(6, 9, 9, 7, 10, 8, 9))
        self.assertEqual(s.verdict, PASS_WITH_REVISIONS)
        self.assertEqual(s.below_threshold, ["body_of_work_depth"])

    def test_placement_and_continuity_threshold_is_6(self):
        self.assertEqual(score_seat(vec(9, 9, 9, 9, 10, 6, 6)).verdict, PASS)
        self.assertEqual(score_seat(vec(9, 9, 9, 9, 10, 5, 9)).verdict, PASS_WITH_REVISIONS)

    def test_sofia_lume_anthropic_is_fail_and_council_veto(self):
        d = legacy("cohort-phase-0", "sofia-lume", "anthropic_chair")
        s = score_seat(d["criterion_scores"])
        self.assertEqual(s.verdict, FAIL)
        self.assertEqual(s.vetoes, ["body_of_work_depth 4 < 5"])
        outcomes = [scoring.SeatOutcome("anthropic_chair", "ok", s)]
        for seat in ("cerebras_reasoning", "moonshot_longctx", "groq_velocity"):
            other = score_seat(legacy("cohort-phase-0", "sofia-lume", seat)["criterion_scores"])
            self.assertEqual(other.verdict, PASS)  # three seats pass her ...
            outcomes.append(scoring.SeatOutcome(seat, "ok", other))
        dec = scoring.decide_council(outcomes, scoring.QuorumRule(voting_seats=(
            "anthropic_chair", "cerebras_reasoning", "moonshot_longctx", "groq_velocity")))
        self.assertEqual(dec.outcome, scoring.OUTCOME_VETO)  # ... and she is still not certified
        self.assertEqual(dec.tally, "3/4")

    def test_recorded_verdicts_reproduced_for_revisions(self):
        for slug in ("lucia-solari", "noa-cifratti"):
            d = legacy("cohort-phase-0", slug, "anthropic_chair")
            self.assertEqual(d["verdict"], PASS_WITH_REVISIONS)
            self.assertEqual(score_seat(d["criterion_scores"]).verdict, PASS_WITH_REVISIONS, slug)

    def test_tariq_recorded_pass_is_revisions_by_rule(self):
        d = legacy("cohort-phase-0", "tariq-al-khwarizmi", "anthropic_chair")
        self.assertEqual(d["verdict"], PASS)
        self.assertEqual(score_seat(d["criterion_scores"]).verdict, PASS_WITH_REVISIONS)


class Validation(unittest.TestCase):
    def test_rejects_missing_bool_range_extra(self):
        good = vec(9, 9, 9, 9, 10, 8, 9)
        for bad in (
            {k: v for k, v in good.items() if k != "placement_fit"},
            {**good, "placement_fit": True},
            {**good, "placement_fit": 11},
            {**good, "placement_fit": 7.5},
            {**good, "overall_score": 9},
        ):
            with self.assertRaises(ScoreError):
                score_seat(bad)

    def test_accepts_legacy_shape(self):
        self.assertEqual(score_seat({k: {"score": v, "rationale": "x"} for k, v in vec(9, 9, 9, 9, 10, 8, 9).items()}).verdict, PASS)


class EvidenceCap(unittest.TestCase):
    def test_zero_artifacts_caps_body_of_work_at_3_and_vetoes(self):
        caps = evidence_caps({"artifact_count": 0})
        s = score_seat(vec(10, 10, 10, 10, 10, 10, 10), caps)
        self.assertEqual(s.scores_raw["body_of_work_depth"], 10)
        self.assertEqual(s.scores_effective["body_of_work_depth"], 3)
        self.assertEqual(s.verdict, FAIL)
        self.assertEqual(s.vetoes, ["body_of_work_depth 3 < 5"])
        self.assertEqual(s.caps_applied[0]["from"], 10)

    def test_no_manifest_is_zero_evidence(self):
        self.assertEqual(len(evidence_caps(None)), 1)

    def test_artifacts_lift_the_cap(self):
        self.assertEqual(evidence_caps({"artifact_count": 3}), [])

    def test_cap_never_raises_a_score(self):
        s = score_seat(vec(2, 9, 9, 9, 10, 8, 9), [Cap("body_of_work_depth", 3, "x")])
        self.assertEqual(s.scores_effective["body_of_work_depth"], 2)
        self.assertEqual(s.caps_applied, [])


if __name__ == "__main__":
    unittest.main()
