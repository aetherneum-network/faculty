"""Executor rule EX-1 (Rector decision D19, 2026-09-30).

"veto until every declared scenario passes; zero scenarios started counts as
zero artifacts"

The rule lives in ``council/council.json``; ``council_v2/rules.py`` only
extracts it.  One test per clause, at three levels: the rule on a summary,
the scoring functions, and the whole dry-run pipeline (signed records,
verification, Registry).  Offline, mock seats, ephemeral keys.
"""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from council_v2 import registry, rules, scoring
from council_v2 import run_council_v2 as rc
from council_v2.legacy import legacy_records
from council_v2.record import executor_ruling_from_records, load_records, seat_outcome_from_record, write_signed
from council_v2.signing import Ed25519Signer, verify_record
from tests.helpers import FACULTY, FIXTURES, vec

COUNCIL = registry.load_council(FACULTY / "council" / "council.json")
RULE = rules.ExecutorRule.from_council(COUNCIL)
TEXT = "veto until every declared scenario passes; zero scenarios started counts as zero artifacts"
APPROVED = "Rector decision D19, 2026-09-30"
QUORUM = scoring.QuorumRule(voting_seats=("anthropic", "reasoning", "longctx", "velocity"))

PASS_PY = "raise SystemExit(0)\n"
FAIL_PY = "raise SystemExit(1)\n"
SLOW_PY = "import time\ntime.sleep(30)\n"


def summary(found=0, passed=0, failed=0, errors=0, timeouts=0, not_passed=(), error=None):
    return {"executor": rules.RAN, "error": error,
            "counts": {"scenarios_found": found, "passed": passed, "failed": failed, "errors": errors, "timeouts": timeouts},
            "not_passed": [{"scenario_id": s, "status": st} for s, st in not_passed]}


def ok_seat(sid, scores=None):
    return scoring.SeatOutcome(sid, "ok", scoring.score_seat(scores or vec(8, 8, 8, 8, 10, 7, 8)))


def make_repo(root: Path, scenarios: dict[str, dict[str, str]] | None) -> Path:
    """A small candidate repository with code (so it has artifacts) and the given scenarios.

    ``scenarios`` maps a scenario id to its files; ``None`` means no ``scenarios/`` directory at all.
    """
    repo = root / "pack"
    (repo / "src").mkdir(parents=True)
    (repo / "README.md").write_text("# Synthetic pack\n\nA synthetic repository used by the executor-rule tests.\n", encoding="utf-8")
    (repo / "src" / "app.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    for sid, files in (scenarios or {}).items():
        d = repo / "scenarios" / sid
        d.mkdir(parents=True)
        for name, body in files.items():
            (d / name).write_text(body, encoding="utf-8")
    return repo


class RuleIsReadFromTheFile(unittest.TestCase):
    """R7: the rule is written in council.json, the code extracts it."""

    def test_rule_as_written(self):
        rule = next(r for r in COUNCIL["rules"] if r["id"] == "EX-1")
        self.assertEqual(rule["text"], TEXT)
        self.assertEqual(rule["approved"], APPROVED)
        self.assertEqual([c["id"] for c in rule["clauses"]], ["EX-1.a", "EX-1.b", "EX-1.c"])
        self.assertEqual("; ".join(c["text"] for c in rule["clauses"][:2]), TEXT)  # the first two clauses are the approved wording
        self.assertEqual((RULE.rule_id, RULE.text, RULE.approved), ("EX-1", TEXT, APPROVED))
        self.assertTrue(RULE.live_requires_executor)

    def test_crash_clause_as_written(self):
        # added after D19 by a ruling on the rule's gap; it carries its own approval line, not the Rector's
        clause = next(r for r in COUNCIL["rules"] if r["id"] == "EX-1")["clauses"][2]
        self.assertEqual((clause["when"], clause["effect"]), ({"executor_crashed": True}, {"outcome": "VETO"}))
        self.assertEqual(clause["text"], "the executor ran and crashed: the number of declared scenarios is unknown, "
                                         "the outcome is VETO")
        self.assertTrue(clause["approved"].startswith("Rector decision D23, 2026-09-30"))
        self.assertNotEqual(clause["approved"], APPROVED)
        self.assertEqual((RULE.crash_clause_id, RULE.crash_approved), ("EX-1.c", clause["approved"]))

    def test_open_question_is_resolved_not_deleted(self):
        q = [x for x in COUNCIL["open_questions"] if "failing scenarios (executor)" in x]
        self.assertEqual(len(q), 1)
        self.assertTrue(q[0].startswith("RESOLVED by rule EX-1"))
        self.assertIn("Whether failing scenarios (executor) should cap body_of_work_depth", q[0])
        self.assertEqual(len(COUNCIL["open_questions"]), 3)

    def test_changing_the_file_changes_the_behaviour(self):
        failing = summary(found=2, passed=1, failed=1, not_passed=[("S02", "fail")])
        self.assertTrue(RULE.evaluate(failing).veto)
        edited = copy.deepcopy(COUNCIL)
        edited["rules"][0]["id"] = "EX-9"
        edited["rules"][0]["clauses"] = [c for c in edited["rules"][0]["clauses"] if c["id"] != "EX-1.a"]
        ruling = rules.ExecutorRule.from_council(edited).evaluate(failing)
        self.assertEqual((ruling.rule_id, ruling.veto, ruling.fired), ("EX-9", False, False))
        no_rules = {k: v for k, v in COUNCIL.items() if k != "rules"}
        self.assertIsNone(rules.ExecutorRule.from_council(no_rules))
        self.assertIsNone(rules.ruling_for(no_rules, failing))

    def test_first_executor_rule_wins(self):
        edited = copy.deepcopy(COUNCIL)
        later = copy.deepcopy(edited["rules"][0])
        later["id"] = "EX-2"
        edited["rules"].append(later)
        self.assertEqual(rules.ExecutorRule.from_council(edited).rule_id, "EX-1")

    def test_a_rule_the_code_cannot_apply_is_an_error_not_ignored(self):
        edited = copy.deepcopy(COUNCIL)
        edited["rules"][0]["clauses"][0]["when"]["phase_of_the_moon"] = "full"
        with self.assertRaises(rules.RuleError):
            rules.ExecutorRule.from_council(edited)
        edited = copy.deepcopy(COUNCIL)
        edited["rules"][0]["exceptions"] = []
        with self.assertRaises(rules.RuleError):  # executor not run and no exception written for it
            rules.ExecutorRule.from_council(edited).evaluate(rules.executor_summary(False, None))


class RuleOnASummary(unittest.TestCase):
    def test_all_pass_rule_silent(self):
        r = RULE.evaluate(summary(found=4, passed=4))
        self.assertEqual((r.fired, r.veto, r.zero_artifacts, r.clauses_fired), (False, False, False, []))
        self.assertEqual(r.counts["started"], 4)

    def test_one_fail_veto(self):
        r = RULE.evaluate(summary(found=4, passed=3, failed=1, not_passed=[("S03", "fail")]))
        self.assertEqual((r.veto, r.zero_artifacts, r.clauses_fired), (True, False, ["EX-1.a"]))
        self.assertIn("EX-1", r.veto_reason)
        self.assertIn("S03 (fail)", r.veto_reason)
        self.assertIn(APPROVED, r.veto_reason)

    def test_one_timeout_veto(self):
        r = RULE.evaluate(summary(found=4, passed=3, timeouts=1, not_passed=[("S04", "timeout")]))
        self.assertEqual((r.veto, r.zero_artifacts, r.clauses_fired), (True, False, ["EX-1.a"]))
        self.assertIn("S04 (timeout)", r.veto_reason)

    def test_one_error_among_passes_is_a_veto_without_the_cap(self):
        r = RULE.evaluate(summary(found=4, passed=3, errors=1, not_passed=[("S02", "error")]))
        self.assertEqual((r.veto, r.zero_artifacts), (True, False))

    def test_zero_found_counts_as_zero_artifacts_without_executor_veto(self):
        r = RULE.evaluate(rules.executor_summary(True, None))  # no scenarios/ directory
        self.assertEqual((r.veto, r.zero_artifacts, r.artifact_count_as, r.clauses_fired), (False, True, 0, ["EX-1.b"]))
        self.assertIn("zero scenarios started", r.cap_reason)

    def test_found_but_none_launchable_cap_and_veto(self):
        ids = [f"S{i:02d}" for i in range(1, 11)]
        r = RULE.evaluate(summary(found=10, errors=10, not_passed=[(s, "error") for s in ids]))
        self.assertEqual((r.veto, r.zero_artifacts, r.clauses_fired), (True, True, ["EX-1.a", "EX-1.b"]))
        self.assertEqual(r.counts["started"], 0)
        self.assertEqual(r.veto_short, "EX-1.a: 10 of 10 declared scenarios not passed")

    def test_started_but_failed_is_not_zero_started(self):
        r = RULE.evaluate(summary(found=2, failed=1, timeouts=1, not_passed=[("A", "fail"), ("B", "timeout")]))
        self.assertEqual((r.veto, r.zero_artifacts, r.counts["started"]), (True, False, 2))

    def test_not_run_rule_silent(self):
        r = RULE.evaluate(rules.executor_summary(False, None))
        self.assertEqual((r.executor, r.fired, r.veto, r.zero_artifacts, r.exception), ("not run", False, False, False, "EX-1.x"))
        self.assertIsNone(r.counts)

    def test_summary_from_an_executor_result(self):
        result = {"scenarios_found": 3, "passed": 1, "failed": 1, "errors": 0, "timeouts": 1,
                  "results": [{"scenario_id": "a", "status": "pass"}, {"scenario_id": "b", "status": "fail"},
                              {"scenario_id": "c", "status": "timeout"}]}
        s = rules.executor_summary(True, result)
        self.assertEqual(s["not_passed"], [{"scenario_id": "b", "status": "fail"}, {"scenario_id": "c", "status": "timeout"}])
        self.assertEqual(s["counts"], {"scenarios_found": 3, "passed": 1, "failed": 1, "errors": 0, "timeouts": 1})

    # ---- clause EX-1.c: the executor itself crashed
    def test_a_crash_is_a_veto_that_names_the_rule(self):
        s = rules.executor_summary(True, None, "RuntimeError: boom")
        self.assertEqual((s["executor"], s["crashed"], s["error"]), ("ran", True, "RuntimeError: boom"))
        r = RULE.evaluate(s)
        self.assertEqual((r.veto, r.crashed, r.zero_artifacts, r.clauses_fired), (True, True, True, ["EX-1.b", "EX-1.c"]))
        self.assertEqual(r.veto_short, "EX-1.c: the executor crashed, declared scenarios unknown")
        self.assertTrue(r.veto_reason.startswith("EX-1 veto (EX-1.c, Rector decision D23, 2026-09-30"))
        self.assertIn("the executor ran and crashed (RuntimeError: boom)", r.veto_reason)
        self.assertIn("the number of declared scenarios is unknown", r.veto_reason)

    def test_nothing_to_execute_is_not_a_crash(self):
        s = rules.executor_summary(True, None)
        self.assertNotIn("crashed", s)  # the summary of a run without scenarios is what it was under D19
        r = RULE.evaluate(s)
        self.assertEqual((r.veto, r.crashed, r.clauses_fired), (False, False, ["EX-1.b"]))
        self.assertFalse(RULE.evaluate(summary(found=4, passed=4)).crashed)
        self.assertFalse(RULE.evaluate(rules.executor_summary(False, None)).crashed)

    def test_a_crash_summary_signed_before_the_clause_is_read_as_a_crash(self):
        old = {"executor": "ran", "counts": {"scenarios_found": 0, "passed": 0, "failed": 0, "errors": 0, "timeouts": 0},
               "not_passed": [], "error": "OSError: disk"}  # the D19 shape: no "crashed" key
        r = RULE.evaluate(old)
        self.assertEqual((r.veto, r.crashed, r.clauses_fired), (True, True, ["EX-1.b", "EX-1.c"]))
        old_nothing = {**old, "error": rules.NOTHING_TO_EXECUTE}
        self.assertEqual((RULE.evaluate(old_nothing).veto, RULE.evaluate(old_nothing).crashed), (False, False))

    def test_a_crash_is_never_more_lenient_than_a_failure(self):
        failing = RULE.evaluate(summary(found=1, failed=1, not_passed=[("S01", "fail")]))
        crashed = RULE.evaluate(rules.executor_summary(True, None, "RuntimeError: boom"))
        seats = [ok_seat(s) for s in QUORUM.voting_seats]
        self.assertEqual(scoring.decide_council(seats, QUORUM, failing).outcome, scoring.OUTCOME_VETO)
        d = scoring.decide_council(seats, QUORUM, crashed)
        self.assertEqual(d.outcome, scoring.OUTCOME_VETO)
        self.assertEqual(d.vetoes, {"executor": ["EX-1.c: the executor crashed, declared scenarios unknown"]})
        self.assertTrue(any("EX-1" in r and "crashed" in r for r in d.reasons))
        self.assertTrue(scoring.evidence_caps({"artifact_count": 12}, crashed))  # and the zero-artifact cap as well
        self.assertEqual(scoring.evidence_caps({"artifact_count": 12}, failing), [])

    def test_without_the_crash_clause_a_crash_is_what_it_was_under_d19(self):
        edited = copy.deepcopy(COUNCIL)
        edited["rules"][0]["clauses"] = [c for c in edited["rules"][0]["clauses"] if c["id"] != "EX-1.c"]
        r = rules.ExecutorRule.from_council(edited).evaluate(rules.executor_summary(True, None, "RuntimeError: boom"))
        self.assertEqual((r.veto, r.clauses_fired), (False, ["EX-1.b"]))  # the code only extracts: no clause, no veto
        edited = copy.deepcopy(COUNCIL)
        edited["rules"][0]["clauses"][2]["effect"] = {"outcome": "PASS"}
        with self.assertRaises(rules.RuleError):
            rules.ExecutorRule.from_council(edited)


class ScoringReadsTheRuling(unittest.TestCase):
    def test_zero_started_caps_like_zero_artifacts(self):
        ruling = RULE.evaluate(summary(found=10, errors=10))
        caps = scoring.evidence_caps({"artifact_count": 12}, ruling)
        self.assertEqual([(c.criterion, c.cap) for c in caps], [("body_of_work_depth", 3)])
        self.assertIn("EX-1", caps[0].reason)
        s = scoring.score_seat(vec(9, 9, 9, 9, 10, 9, 9), caps)
        self.assertEqual(s.verdict, scoring.FAIL)
        self.assertTrue(s.vetoes)

    def test_no_ruling_or_silent_ruling_leaves_the_caps_alone(self):
        self.assertEqual(scoring.evidence_caps({"artifact_count": 12}), [])
        self.assertEqual(scoring.evidence_caps({"artifact_count": 12}, None), [])
        self.assertEqual(scoring.evidence_caps({"artifact_count": 12}, RULE.evaluate(summary(found=4, passed=4))), [])
        self.assertEqual(scoring.evidence_caps({"artifact_count": 12}, RULE.evaluate(rules.executor_summary(False, None))), [])
        # a fail is a veto (EX-1.a) but scenarios did start: no artifact cap
        self.assertEqual(scoring.evidence_caps({"artifact_count": 12}, RULE.evaluate(summary(found=4, passed=3, failed=1))), [])
        # the pre-existing zero-artifact reason is kept when the repository really has none
        old = scoring.evidence_caps({"artifact_count": 0})
        self.assertEqual([c.__dict__ for c in scoring.evidence_caps({"artifact_count": 0}, RULE.evaluate(summary()))],
                         [c.__dict__ for c in old])

    def test_executor_veto_whatever_the_seats_scored(self):
        ruling = RULE.evaluate(summary(found=4, passed=3, failed=1, not_passed=[("S03", "fail")]))
        seats = [ok_seat(s) for s in QUORUM.voting_seats]
        self.assertEqual(scoring.decide_council(seats, QUORUM).outcome, scoring.OUTCOME_PASS)
        d = scoring.decide_council(seats, QUORUM, ruling)
        self.assertEqual(d.outcome, scoring.OUTCOME_VETO)
        self.assertEqual(d.vetoes, {"executor": ["EX-1.a: 1 of 4 declared scenarios not passed"]})
        self.assertEqual((d.pass_count, d.tally), (4, "4/4"))  # the seats' scores are still reported as they are
        self.assertTrue(any("EX-1" in r and "S03 (fail)" in r for r in d.reasons))

    def test_executor_veto_is_decided_before_quorum(self):
        ruling = RULE.evaluate(summary(found=1, failed=1, not_passed=[("S01", "fail")]))
        seats = [ok_seat("anthropic"), scoring.SeatOutcome("reasoning", "null"), scoring.SeatOutcome("longctx", "null")]
        self.assertEqual(scoring.decide_council(seats, QUORUM).outcome, scoring.OUTCOME_NO_QUORUM)
        d = scoring.decide_council(seats, QUORUM, ruling)
        self.assertEqual(d.outcome, scoring.OUTCOME_VETO)
        self.assertTrue(any("quorum not reached either" in r for r in d.reasons))

    def test_silent_or_absent_ruling_changes_nothing(self):
        seats = [ok_seat(s) for s in QUORUM.voting_seats]
        base = scoring.decide_council(seats, QUORUM).to_dict()
        for ruling in (None, RULE.evaluate(summary(found=4, passed=4)), RULE.evaluate(rules.executor_summary(False, None)),
                       RULE.evaluate(rules.executor_summary(True, None))):
            self.assertEqual(scoring.decide_council(seats, QUORUM, ruling).to_dict(), base)


class _Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.signer = Ed25519Signer.generate("test")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, scenarios, **kw):
        repo = kw.pop("repo", None) or make_repo(self.root, scenarios)
        args = dict(repos_root=FACULTY.parent, out_root=self.root / "records", signer=self.signer, dry_run=True, mock=True,
                    intake=None, profile=repo / "README.md", repo=repo, seats=rc.build_mock_seats(COUNCIL),
                    with_calibration=False)
        args.update(kw)
        return rc.run("pack", **args)

    def _decision(self, s):
        return json.loads((Path(s["out"]) / "pack__DECISION.json").read_text(encoding="utf-8"))


class Pipeline(_Run):
    def test_all_pass_rule_silent(self):
        s = self._run({"S01": {"run.py": PASS_PY}, "S02": {"run.py": PASS_PY}})
        self.assertEqual(s["decision"]["outcome"], "PASS")
        self.assertEqual(s["decision"]["vetoes"], {})
        self.assertEqual(s["caps"], [])
        ex = s["executor_rule"]
        self.assertEqual((ex["rule_id"], ex["fired"], ex["veto"], ex["executor"]), ("EX-1", False, False, "ran"))
        self.assertEqual((ex["counts"]["scenarios_found"], ex["counts"]["passed"], ex["counts"]["started"]), (2, 2, 2))

    def test_one_fail_is_a_veto_although_every_mock_seat_passes(self):
        s = self._run({"S01": {"run.py": PASS_PY}, "S02": {"run.py": FAIL_PY}})
        d = s["decision"]
        self.assertEqual((d["outcome"], d["pass_count"]), ("VETO", 4))  # the mock scorer ignores the executor; the rule does not
        self.assertEqual(d["vetoes"], {"executor": ["EX-1.a: 1 of 2 declared scenarios not passed"]})
        self.assertTrue(any("EX-1" in r and "S02 (fail)" in r for r in d["reasons"]))
        self.assertEqual(s["caps"], [])  # a scenario started: no artifact cap
        self.assertEqual(s["executor_rule"]["clauses_fired"], ["EX-1.a"])

    def test_one_timeout_is_a_veto(self):
        s = self._run({"S01": {"run.py": PASS_PY},
                       "S02": {"scenario.json": json.dumps({"run": ["python", "slow.py"], "timeout_s": 1}), "slow.py": SLOW_PY}})
        self.assertEqual(s["decision"]["outcome"], "VETO")
        self.assertEqual(s["executor_rule"]["not_passed"], [{"scenario_id": "S02", "status": "timeout"}])
        self.assertEqual(s["executor_rule"]["counts"]["timeouts"], 1)
        self.assertEqual(s["caps"], [])

    def test_zero_found_is_the_zero_artifact_cap(self):
        s = self._run(None)  # code, no scenarios/ directory
        self.assertEqual([(c["criterion"], c["cap"]) for c in s["caps"]], [("body_of_work_depth", 3)])
        self.assertIn("EX-1", s["caps"][0]["reason"])
        ex = s["executor_rule"]
        self.assertEqual((ex["veto"], ex["zero_artifacts"], ex["clauses_fired"]), (False, True, ["EX-1.b"]))
        self.assertEqual(ex["counts"]["scenarios_found"], 0)
        d = s["decision"]
        self.assertEqual(d["outcome"], "VETO")  # through the cap: every seat's body_of_work_depth 8 -> 3
        self.assertNotIn("executor", d["vetoes"])
        self.assertEqual(sorted(d["vetoes"]), sorted(QUORUM.voting_seats))

    def test_found_but_none_launchable_is_cap_and_veto(self):
        # the Costanza v2 shape: scenario directories with a check script and nothing the executor can launch
        s = self._run({f"S{i:02d}": {"check.py": PASS_PY, "README.md": "scenario\n"} for i in range(1, 4)})
        ex = s["executor_rule"]
        self.assertEqual((ex["veto"], ex["zero_artifacts"], ex["clauses_fired"]), (True, True, ["EX-1.a", "EX-1.b"]))
        self.assertEqual((ex["counts"]["scenarios_found"], ex["counts"]["errors"], ex["counts"]["started"]), (3, 3, 0))
        self.assertEqual([(c["criterion"], c["cap"]) for c in s["caps"]], [("body_of_work_depth", 3)])
        d = s["decision"]
        self.assertEqual(d["outcome"], "VETO")
        self.assertEqual(d["vetoes"]["executor"], ["EX-1.a: 3 of 3 declared scenarios not passed"])
        self.assertEqual(sorted(k for k in d["vetoes"] if k != "executor"), sorted(QUORUM.voting_seats))

    def test_a_crash_of_the_scenario_runner_is_a_veto(self):
        def boom(*a, **kw):
            raise RuntimeError("runner broke")

        with mock.patch.object(rc, "run_scenarios", boom):
            s = self._run({"S01": {"run.py": PASS_PY}})  # a pack that would pass: the crash must not read as a pass
        ex = s["executor_rule"]
        self.assertEqual((ex["executor"], ex["crashed"], ex["veto"], ex["clauses_fired"]), ("ran", True, True, ["EX-1.b", "EX-1.c"]))
        d = s["decision"]
        self.assertEqual((d["outcome"], d["pass_count"]), ("VETO", 0))  # the zero-artifact cap fails every seat as well
        self.assertEqual(d["vetoes"]["executor"], ["EX-1.c: the executor crashed, declared scenarios unknown"])
        self.assertTrue(any(r.startswith("EX-1 veto (EX-1.c") and "RuntimeError: runner broke" in r for r in d["reasons"]))
        signed = self._decision(s)
        self.assertTrue(verify_record(signed, self.signer.public_key).ok)
        self.assertEqual(signed["executor_rule"]["clauses_fired"], ["EX-1.b", "EX-1.c"])
        executor_record = json.loads((Path(s["out"]) / "pack__executor.json").read_text(encoding="utf-8"))
        self.assertIn("RuntimeError: runner broke", json.dumps(executor_record))  # the crash is written down, signed
        recs, rejected = load_records([s["out"]], self.signer.public_key)
        self.assertEqual(rejected, [])
        row = registry.build_rows(recs, COUNCIL, include_mock=True)[0]
        self.assertEqual(row.decision.outcome, "VETO")
        self.assertIn("EX-1.c", json.dumps(row.decision.vetoes))

    def test_dry_run_without_executor_says_not_run_and_carries_no_executor_veto(self):
        s = self._run({"S01": {"run.py": FAIL_PY}}, run_executor=False)
        self.assertEqual(s["decision"]["outcome"], "PASS")
        self.assertEqual(s["decision"]["vetoes"], {})
        self.assertEqual(s["caps"], [])
        ex = self._decision(s)["executor_rule"]
        self.assertEqual((ex["executor"], ex["fired"], ex["veto"], ex["exception"]), ("not run", False, False, "EX-1.x"))
        seat = json.loads((Path(s["out"]) / "pack__anthropic.json").read_text(encoding="utf-8"))
        self.assertEqual(seat["executor"]["executor"], "not run")
        self.assertEqual(list(Path(s["out"]).glob("*__executor.json")), [])  # nothing pretends the executor ran

    def test_live_without_executor_is_refused_before_anything_is_written(self):
        with self.assertRaises(rc.RunRefused) as cm:
            self._run({"S01": {"run.py": PASS_PY}}, dry_run=False, mock=False, run_executor=False)
        self.assertIn("EX-1", str(cm.exception))
        self.assertIn("--no-executor", str(cm.exception))
        self.assertEqual(list((self.root / "records").rglob("*.json")) if (self.root / "records").exists() else [], [])

    def test_cli_refuses_live_with_no_executor(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = rc.main(["--slug", "tiny-repo", "--live", "--no-executor"])
        self.assertEqual(code, 2)
        self.assertIn("--live together with --no-executor is not allowed", err.getvalue())
        self.assertIn("EX-1", err.getvalue())
        self.assertIn(APPROVED, err.getvalue())


class SignedRecordAndRegistry(_Run):
    def test_decision_record_carries_counts_rule_id_and_fired_and_verifies(self):
        s = self._run({"S01": {"run.py": PASS_PY}, "S02": {"run.py": FAIL_PY}})
        dec = self._decision(s)
        ex = dec["executor_rule"]
        self.assertEqual((ex["rule_id"], ex["approved"], ex["text"]), ("EX-1", APPROVED, TEXT))
        self.assertEqual(ex["counts"], {"scenarios_found": 2, "passed": 1, "failed": 1, "errors": 0, "timeouts": 0, "started": 2})
        self.assertEqual((ex["fired"], ex["veto"], ex["clauses_fired"]), (True, True, ["EX-1.a"]))
        recs, rejected = load_records([s["out"]], self.signer.public_key)
        self.assertEqual(rejected, [])
        self.assertEqual(len(recs), 4 + 1 + 1)  # four seats, executor, decision
        self.assertTrue(verify_record(dec, self.signer.public_key).ok)
        dec["executor_rule"]["fired"] = False  # editing the ruling after signing is detected
        self.assertFalse(verify_record(dec, self.signer.public_key).ok)
        seat = json.loads((Path(s["out"]) / "pack__velocity.json").read_text(encoding="utf-8"))
        seat["executor"]["counts"]["passed"] = 2  # and so is editing the rule's input in a seat record
        self.assertFalse(verify_record(seat, self.signer.public_key).ok)

    def test_registry_row_shows_the_executor_veto(self):
        s = self._run({"S01": {"run.py": PASS_PY}, "S02": {"run.py": FAIL_PY}})
        rows, rejected = registry.build([s["out"]], self.signer.public_key, COUNCIL, include_mock=True)
        self.assertEqual(rejected, [])
        row = rows[0]
        self.assertEqual(row.decision.outcome, "VETO")
        # the Registry recomputes the decision from the seat records; it equals the signed decision record
        self.assertEqual(json.loads(json.dumps(row.decision.to_dict())), self._decision(s)["decision"])
        line = next(ln for ln in registry.to_markdown(rows, COUNCIL).splitlines() if ln.startswith("| ") and "pack" in ln)
        self.assertIn("| VETO |", line)
        self.assertIn("executor: EX-1.a: 1 of 2 declared scenarios not passed", line)
        self.assertIn("executor: EX-1.a: 1 of 2 declared scenarios not passed", registry.to_html(rows, COUNCIL))
        self.assertIn('class="outcome-veto registry-mock"', registry.to_html(rows, COUNCIL))

    def test_registry_row_without_executor_has_no_executor_veto(self):
        s = self._run({"S01": {"run.py": FAIL_PY}}, run_executor=False)
        rows, _ = registry.build([s["out"]], self.signer.public_key, COUNCIL, include_mock=True)
        self.assertEqual((rows[0].decision.outcome, rows[0].decision.vetoes), ("PASS", {}))

    def test_registry_uses_the_rule_of_the_council_file_it_is_given(self):
        s = self._run({"S01": {"run.py": FAIL_PY}})
        no_rules = {k: v for k, v in COUNCIL.items() if k != "rules"}
        rows, _ = registry.build([s["out"]], self.signer.public_key, no_rules, include_mock=True)
        self.assertEqual(rows[0].decision.outcome, "PASS")  # no rule in the file -> no rule applied: the code only extracts


class LegacyOutcomesUnchanged(unittest.TestCase):
    """The 2026 JSON have no executor result: recomputing them must give exactly what it gave before EX-1."""

    def test_legacy_records_carry_no_executor_summary_and_get_no_ruling(self):
        lmap = registry.legacy_map(COUNCIL)
        n = 0
        for cohort in ("cohort-2026", "cohort-q2-2026"):
            if not (FACULTY / cohort / "council-reviews").is_dir():
                continue
            recs = list(legacy_records(FACULTY, cohort, v2_seat_map=lmap))
            n += len(recs)
            self.assertTrue(all("executor" not in r for r in recs))
            self.assertEqual(executor_ruling_from_records(recs, COUNCIL), (None, []))
        self.assertGreater(n, 0)

    def test_legacy_registry_rows_are_identical_with_and_without_the_rule(self):
        signer = Ed25519Signer.generate("test")
        lmap = registry.legacy_map(COUNCIL)
        no_rules = {k: v for k, v in COUNCIL.items() if k != "rules"}
        with tempfile.TemporaryDirectory() as td:
            for r in legacy_records(FACULTY, "cohort-q2-2026", v2_seat_map=lmap):
                write_signed(r, Path(td) / f"{r['candidate']['slug']}__{r['seat']['legacy_seat_id']}.json", signer)
            with_rule, _ = registry.build([td], signer.public_key, COUNCIL)
            without, _ = registry.build([td], signer.public_key, no_rules)
        self.assertTrue(with_rule)
        self.assertEqual([(r.slug, r.decision.to_dict(), r.seats) for r in with_rule],
                         [(r.slug, r.decision.to_dict(), r.seats) for r in without])
        self.assertEqual(registry.to_markdown(with_rule, COUNCIL), registry.to_markdown(without, no_rules))

    def test_default_arguments_keep_the_old_behaviour(self):
        outcomes = [ok_seat(s) for s in QUORUM.voting_seats[:3]] + [scoring.SeatOutcome("velocity", "null", error="timeout")]
        self.assertEqual(scoring.decide_council(outcomes, QUORUM).to_dict(), scoring.decide_council(outcomes, QUORUM, None).to_dict())
        self.assertEqual(scoring.evidence_caps({"artifact_count": 3}), [])
        self.assertEqual(len(scoring.evidence_caps(None)), 1)
        rec_like = {"seat": {"seat_id": "anthropic"}, "status": "ok", "scores_raw": vec(8, 8, 8, 8, 10, 7, 8), "caps": []}
        self.assertEqual(seat_outcome_from_record(rec_like).score.verdict, scoring.PASS)


if __name__ == "__main__":
    unittest.main()
