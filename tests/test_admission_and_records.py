"""Rules P3 and P4 (Rector, 2026-09-30) in the pipeline, the signed decision record and the Registry.

* P4: a live defence without a proof pack, or with a pack the executor vetoes, is refused before any
  seat is called; a mock / dry-run session runs and its decision record says the rule would have refused.
* P3: the decision record signs ``certified_until`` and the digest of the scorecard; the Registry row
  shows status and expiry; a mock, dry-run or "executor: not run" record never reads as certified.
* Backward compatibility: records signed before this change still verify and build a Registry; the
  legacy recomputation gives what it gave before.

Offline, mock seats, ephemeral keys, synthetic packs.  "Live" here is ``dry_run=False`` with mock
seats: nothing is called outside this process.
"""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from council_v2 import registry, rules, scorecard, scoring
from council_v2 import run_council_v2 as rc
from council_v2.legacy import legacy_records
from council_v2.record import (ADMISSION_REFUSED_SCHEMA, DECISION_SCHEMA, SEAT_SCHEMA, build_decision_record, load_records,
                               write_signed)
from council_v2.signing import Ed25519Signer, load_public_key, verify_record
from tests.helpers import FACULTY, FIXTURES, vec
from tests.test_executor_rule import FAIL_PY, PASS_PY, make_repo
from tests.test_scorecard import a_card, a_run

COUNCIL = registry.load_council(FACULTY / "council" / "council.json")
P3 = rules.DiplomaRule.from_council(COUNCIL)
P4 = rules.AdmissionRule.from_council(COUNCIL)
APPROVED = "Rector, 2026-09-30"
QUORUM = scoring.QuorumRule(voting_seats=("anthropic", "reasoning", "longctx", "velocity"))
MARKER = "REHEARSAL — mock seats, test key — not a Council verdict"
D0 = date(2026, 10, 1)
SIGNED_AT = "2026-10-01T12:00:00Z"
RAN_ALL_PASS = {"executor": "ran", "counts": {"scenarios_found": 2, "passed": 2, "failed": 0, "errors": 0, "timeouts": 0},
                "not_passed": [], "error": None}
NOT_RUN = {"executor": "not run", "counts": None, "not_passed": [], "error": None}


def day(n: int) -> date:
    return D0 + timedelta(days=n)


class NeverCalledSeat:
    """A seat that fails the test if the pipeline reaches it."""

    def __init__(self, seat_id: str):
        self.seat_id = seat_id

    def score(self, bundle):  # pragma: no cover - must not run
        raise AssertionError(f"seat {self.seat_id} was called: the defence should have been refused before")


class _Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.signer = Ed25519Signer.generate("test")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, scenarios, **kw):
        repo = kw.pop("repo", "make")
        if repo == "make":
            repo = make_repo(self.root, scenarios)
        profile = kw.pop("profile", None) or (repo / "README.md" if repo else FIXTURES / "tiny_repo" / "README.md")
        args = dict(repos_root=FACULTY.parent, out_root=self.root / "records", signer=self.signer, dry_run=True, mock=True,
                    intake=None, profile=profile, repo=repo, seats=rc.build_mock_seats(COUNCIL), with_calibration=False)
        args.update(kw)
        return rc.run("pack", **args)

    def _decision(self, s):
        return json.loads((Path(s["out"]) / "pack__DECISION.json").read_text(encoding="utf-8"))

    def _written(self):
        return sorted(p.name for p in (self.root / "records").rglob("*.json")) if (self.root / "records").exists() else []

    def _card_file(self, runs=None, name="pack.scorecard.json", **over) -> Path:
        doc = a_card(runs or [a_run(day(-1), 1, "protocol"), a_run(day(-1), 2, hh=13)], alumnus="pack", **over)
        p = self.root / name
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        return p


# ======================================================================================================
# P4 — no new alumnus without a proof pack
# ======================================================================================================

class AdmissionRuleIsReadFromTheFile(unittest.TestCase):
    def test_rule_as_written(self):
        rule = next(r for r in COUNCIL["rules"] if r["id"] == "P4")
        self.assertEqual((rule["subject"], rule["approved"]), ("admission", APPROVED))
        self.assertIn("a defence starts only for a candidate whose pack exists and passes the executor", rule["text"])
        self.assertEqual([c["id"] for c in rule["clauses"]], ["P4.a", "P4.b"])
        self.assertEqual([e["id"] for e in rule["exceptions"]], ["P4.x"])
        self.assertEqual((P4.rule_id, P4.approved, P4.pack_clause_id, P4.min_scenarios, P4.executor_clause_id, P4.exception_id),
                         ("P4", APPROVED, "P4.a", 1, "P4.b", "P4.x"))

    def test_changing_the_file_changes_the_behaviour(self):
        no_p4 = {**COUNCIL, "rules": [r for r in COUNCIL["rules"] if r["id"] != "P4"]}
        self.assertIsNone(rules.AdmissionRule.from_council(no_p4))
        edited = copy.deepcopy(COUNCIL)
        next(r for r in edited["rules"] if r["id"] == "P4")["clauses"][0]["when"]["pack_scenarios_below"] = 3
        rule3 = rules.AdmissionRule.from_council(edited)
        self.assertIsNone(P4.pack_refusal(True, 2))
        self.assertIn("at least 3 scenario(s)", rule3.pack_refusal(True, 2))
        edited = copy.deepcopy(COUNCIL)
        next(r for r in edited["rules"] if r["id"] == "P4")["exceptions"] = []  # no dry-run exception written
        strict = rules.AdmissionRule.from_council(edited)
        a = strict.evaluate(repo_given=False, scenarios=0, executor=None, live=False)
        self.assertEqual((a["refused"], a["would_refuse"], a["enforced"]), (True, False, True))

    def test_a_rule_the_code_cannot_apply_is_an_error_not_ignored(self):
        for fn in (lambda r: r["clauses"][0].update(effect="warn"),
                   lambda r: r["clauses"][1].update(when={"phase_of_the_moon": "full"}),
                   lambda r: r["exceptions"][0].update(effect="silent")):
            edited = copy.deepcopy(COUNCIL)
            fn(next(r for r in edited["rules"] if r["id"] == "P4"))
            with self.assertRaises(rules.RuleError):
                rules.AdmissionRule.from_council(edited)


class AdmissionLive(_Run):
    """``dry_run=False`` with seats that must never be reached."""

    def _live(self, scenarios, **kw):
        kw.setdefault("seats", [NeverCalledSeat(s) for s in QUORUM.voting_seats])
        return self._run(scenarios, dry_run=False, mock=False, **kw)

    def test_live_without_a_repo_is_refused_before_anything_is_written(self):
        with self.assertRaises(rc.RunRefused) as cm:
            self._live(None, repo=None)
        self.assertIn("rule P4 (Rector, 2026-09-30), clause P4.a: no --repo given", str(cm.exception))
        self.assertEqual(self._written(), [])

    def test_live_with_a_repo_without_scenarios_is_refused_before_anything_is_written(self):
        with self.assertRaises(rc.RunRefused) as cm:
            self._live(None)  # code, README, no scenarios/ directory
        self.assertIn("P4.a", str(cm.exception))
        self.assertIn("the repository given has 0 scenario(s)", str(cm.exception))
        self.assertEqual(self._written(), [])

    def test_live_with_a_failing_pack_is_refused_before_any_seat_is_called(self):
        with self.assertRaises(rc.RunRefused) as cm:
            self._live({"S01": {"run.py": PASS_PY}, "S02": {"run.py": FAIL_PY}})
        self.assertIn("rule P4 (Rector, 2026-09-30), clause P4.b", str(cm.exception))
        self.assertIn("EX-1.a: 1 of 2 declared scenarios not passed", str(cm.exception))
        self.assertEqual(self._written(), ["pack__ADMISSION_REFUSED.json", "pack__executor.json"])  # no seat, no decision
        recs, rejected = load_records([self.root / "records"], self.signer.public_key)
        self.assertEqual(rejected, [])
        refusal = next(r for r in recs if r["schema"] == ADMISSION_REFUSED_SCHEMA)
        self.assertEqual(refusal["outcome"], "REFUSED_BY_ADMISSION_RULE")
        a = refusal["admission"]
        self.assertEqual((a["rule_id"], a["approved"], a["clauses_fired"], a["refused"], a["enforced"]),
                         ("P4", APPROVED, ["P4.b"], True, True))
        self.assertEqual(registry.build_rows(recs, COUNCIL), [])  # a refusal is not a Registry row

    def test_live_with_an_executor_that_crashes_is_refused_before_any_seat_is_called(self):
        def boom(*a, **kw):
            raise RuntimeError("runner broke")

        with mock.patch.object(rc, "run_scenarios", boom), self.assertRaises(rc.RunRefused) as cm:
            self._live({"S01": {"run.py": PASS_PY}})
        self.assertIn("clause P4.b", str(cm.exception))
        self.assertIn("EX-1.c: the executor crashed, declared scenarios unknown", str(cm.exception))
        self.assertEqual(self._written(), ["pack__ADMISSION_REFUSED.json", "pack__executor.json"])

    def test_live_with_a_passing_pack_starts(self):
        s = self._live({"S01": {"run.py": PASS_PY}}, seats=rc.build_mock_seats(COUNCIL))
        a = s["admission"]
        self.assertEqual((a["admitted"], a["refused"], a["would_refuse"], a["clauses_fired"]), (True, False, False, []))
        self.assertEqual(a["pack"], {"repo_given": True, "scenarios": 1, "min_scenarios": 1})
        self.assertEqual(s["decision"]["outcome"], "PASS")

    def test_cli_refuses_live_without_a_pack_and_names_the_rule(self):
        empty = make_repo(self.root, None)
        for argv, needle in ((["--slug", "pack", "--live"], "no --repo given"),
                             (["--slug", "pack", "--live", "--repo", str(empty)], "the repository given has 0 scenario(s)")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = rc.main(argv)
            self.assertEqual(code, 2)
            self.assertIn("refused: rule P4 (Rector, 2026-09-30), clause P4.a", err.getvalue())
            self.assertIn(needle, err.getvalue())

    def test_cli_reports_every_refusal_not_only_the_first(self):
        # rule P4 is checked before the approval of the spend: neither refusal may hide the others
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = rc.main(["--slug", "pack", "--live", "--no-executor", "--allow-steering", "--marker", MARKER])
        self.assertEqual(code, 2)
        lines = [ln for ln in err.getvalue().splitlines() if ln.startswith("refused: ")]
        self.assertEqual(len(lines), 5)
        for needle in ("--live together with --no-executor is not allowed", "rule P4 (Rector, 2026-09-30), clause P4.a",
                       "live run needs --key, --approval-ref", "--allow-steering is not allowed in a live run",
                       "--marker labels rehearsals and is not allowed in a live run"):
            self.assertEqual(sum(needle in ln for ln in lines), 1, needle)
        # with a pack that has a scenario the admission rule is silent and the approval is still required
        pack = make_repo(self.root, {"S01": {"run.py": PASS_PY}})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = rc.main(["--slug", "pack", "--live", "--repo", str(pack)])
        self.assertEqual(code, 2)
        self.assertNotIn("P4", err.getvalue())
        self.assertIn("refused: live run needs --key, --approval-ref", err.getvalue())

    def test_without_the_rule_in_the_file_nothing_is_refused_by_it(self):
        no_p4 = {**COUNCIL, "rules": [r for r in COUNCIL["rules"] if r["id"] != "P4"]}
        path = self.root / "council_without_p4.json"
        path.write_text(json.dumps(no_p4, ensure_ascii=False), encoding="utf-8")
        s = self._live(None, seats=rc.build_mock_seats(COUNCIL), council_path=path)  # the code only extracts
        self.assertIsNone(s["admission"])


class AdmissionDryRun(_Run):
    def test_no_pack_runs_and_the_record_says_the_rule_would_have_refused(self):
        s = self._run(None)
        a = self._decision(s)["admission"]
        self.assertEqual((a["rule_id"], a["approved"]), ("P4", APPROVED))
        self.assertEqual((a["admitted"], a["refused"], a["would_refuse"], a["enforced"], a["exception"]),
                         (False, False, True, False, "P4.x"))
        self.assertEqual(a["clauses_fired"], ["P4.a"])
        self.assertTrue(any("would have refused" in n for n in a["notes"]))
        self.assertEqual(a["pack"]["scenarios"], 0)
        self.assertTrue(verify_record(self._decision(s), self.signer.public_key).ok)

    def test_no_repo_at_all_runs_and_says_so(self):
        a = self._run(None, repo=None)["admission"]
        self.assertEqual((a["would_refuse"], a["clauses_fired"], a["pack"]["repo_given"]), (True, ["P4.a"], False))

    def test_failing_pack_runs_and_says_so(self):
        s = self._run({"S01": {"run.py": FAIL_PY}})
        a = s["admission"]
        self.assertEqual((a["would_refuse"], a["clauses_fired"], a["executor"]), (True, ["P4.b"], "ran"))
        self.assertEqual(s["decision"]["outcome"], "VETO")

    def test_passing_pack_is_admitted(self):
        a = self._run({"S01": {"run.py": PASS_PY}})["admission"]
        self.assertEqual((a["admitted"], a["would_refuse"], a["clauses_fired"], a["notes"]), (True, False, [], []))

    def test_without_the_executor_the_executor_clause_is_not_checked_and_the_record_says_so(self):
        a = self._run({"S01": {"run.py": FAIL_PY}}, run_executor=False)["admission"]
        self.assertEqual((a["admitted"], a["executor"]), (True, "not run"))
        self.assertEqual(a["notes"], ["P4.b not checked: executor not run"])


# ======================================================================================================
# P3 — what the decision record signs
# ======================================================================================================

def crafted_session(*, executor=RAN_ALL_PASS, mock_session=False, dry_run=False, scores=None, card=None, session_id="s-live",
                    slug="pack"):
    """Seat records and the decision of a session that is NOT mock and NOT a dry run, built in memory.

    No provider is involved: the records are written by hand so that the record builder and the Registry
    can be tested on the shape a real verdict will have.
    """
    session = {"session_id": session_id, "kind": "defense", "started_at": SIGNED_AT, "dry_run": dry_run, "mock": mock_session,
               "council_config_sha256": None, "faculty_commit": None, "approval_ref": "TEST", "signing_key_id": "test"}
    candidate = {"slug": slug, "name": "Synthetic Pack", "specialty": "test fixture", "number": None, "cohort": None}
    seats = []
    for sid in QUORUM.voting_seats:
        rec = {"schema": SEAT_SCHEMA, "session": session, "candidate": candidate,
               "seat": {"seat_id": sid, "role": sid, "voting": True, "provider": "test"}, "status": "ok",
               "scores_raw": scores or vec(8, 8, 8, 8, 10, 7, 8), "caps": [], "scoring": None, "error": None,
               "calibration": {"status": "passed"}, "mock": mock_session, "dry_run": dry_run}
        if executor is not None:
            rec["executor"] = executor
        seats.append(rec)
    admission = P4.evaluate(repo_given=True, scenarios=2, executor=rules.ruling_for(COUNCIL, executor), live=not dry_run)
    with mock.patch("council_v2.record.now", return_value=SIGNED_AT):
        decision = build_decision_record(session, candidate, seats, QUORUM, bundle_sha256=None, council=COUNCIL,
                                         admission=admission, scorecard=card.summary() if card is not None else None)
    return seats, decision


def write_session(td: Path, signer, seats, decision, slug="pack") -> None:
    for r in seats:
        write_signed(dict(r), td / f"{slug}__{r['seat']['seat_id']}.json", signer)
    write_signed(dict(decision), td / f"{slug}__DECISION.json", signer)


def blind_card(runs=None, **over) -> scorecard.Scorecard:
    doc = a_card(runs or [a_run(day(-1), 1)], alumnus="pack", **over)
    raw = json.dumps(doc).encode("utf-8")
    return scorecard.validate(doc, P3, sha256=scorecard.sha256_bytes(raw), source="pack.scorecard.json")


def as_raw(card: scorecard.Scorecard) -> dict[str, scorecard.RawScorecard]:
    return {"pack": scorecard.RawScorecard(data=card.data, sha256=card.sha256, source=card.source)}


class DecisionRecord(_Run):
    def test_a_signed_verdict_gets_certified_until_and_the_scorecard_digest(self):
        card = blind_card()
        _, dec = crafted_session(card=card)
        self.assertEqual(dec["decision"]["outcome"], "PASS")
        self.assertEqual(dec["recorded_at"], SIGNED_AT)
        self.assertEqual(dec["certified_until"], "2026-12-30")  # 2026-10-01 + 90 days
        self.assertEqual(dec["scorecard"]["sha256"], card.sha256)
        self.assertEqual(len(dec["scorecard"]["sha256"]), 64)
        d = dec["diploma_rule"]
        self.assertEqual((d["rule_id"], d["approved"], d["verdict_date"], d["certified_until"], d["not_certified_because"]),
                         ("P3", APPROVED, "2026-10-01", "2026-12-30", []))
        self.assertEqual(d["parameters"]["validity_days"], {"id": "P3.1", "value": 90, "approved": APPROVED})
        signed = json.loads(json.dumps(dec))
        path = write_signed(signed, self.root / "pack__DECISION.json", self.signer)
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(verify_record(stored, self.signer.public_key).ok)
        for key, value in (("certified_until", "2027-12-30"), ("scorecard", {**stored["scorecard"], "sha256": "0" * 64})):
            tampered = {**stored, key: value}  # the expiry and the digest are under the signature
            self.assertFalse(verify_record(tampered, self.signer.public_key).ok)

    def test_no_expiry_without_a_verdict(self):
        card = blind_card()
        cases = [
            (dict(card=card, mock_session=True), "mock"),
            (dict(card=card, dry_run=True), "dry run"),
            (dict(card=card, executor=NOT_RUN), "executor: not run"),
            (dict(card=card, executor=None), "executor: no result"),
            (dict(card=card, scores=vec(8, 8, 8, 8, 10, 7, 3)), "not PASS"),
            (dict(card=None), "relied on no scorecard"),
        ]
        for kw, needle in cases:
            _, dec = crafted_session(**kw)
            self.assertIsNone(dec["certified_until"], needle)
            self.assertIsNone(dec["diploma_rule"]["certified_until"], needle)
            self.assertTrue(any(needle in why for why in dec["diploma_rule"]["not_certified_because"]), needle)
            self.assertEqual(dec["diploma_rule"]["verdict_date_plus_validity"], "2026-12-30")  # what it would have been

    def test_dry_run_pipeline_signs_the_digest_of_the_file_and_no_expiry(self):
        path = self._card_file()
        s = self._run({"S01": {"run.py": PASS_PY}}, scorecard=path, marker=MARKER)
        dec = self._decision(s)
        self.assertEqual(dec["scorecard"]["sha256"], scorecard.sha256_bytes(path.read_bytes()))
        self.assertEqual((dec["scorecard"]["file"], dec["scorecard"]["runs"], dec["scorecard"]["headline_run"]),
                         ("pack.scorecard.json", 2, 1))
        self.assertEqual((dec["scorecard"]["alumnus_is_candidate"], dec["scorecard"]["freeze_commit_is_repo_head"]), (True, None))
        self.assertIsNone(dec["certified_until"])
        self.assertEqual(dec["session"]["marker"], MARKER)
        self.assertTrue(verify_record(dec, self.signer.public_key).ok)
        self.assertEqual(s["certified_until"], None)

    def test_a_scorecard_the_validator_refuses_stops_the_run_before_anything_is_written(self):
        bad = self._card_file([a_run(day(-1), 1), a_run(day(-2), 2)], name="bad.scorecard.json")  # not in date order
        with self.assertRaises(rc.RunRefused) as cm:
            self._run({"S01": {"run.py": PASS_PY}}, scorecard=bad)
        self.assertIn("refused (rule P3)", str(cm.exception))
        self.assertIn("run-order", str(cm.exception))
        self.assertEqual(self._written(), [])

    def test_the_scorecard_of_another_alumnus(self):
        other = self._card_file(name="other.scorecard.json")
        doc = json.loads(other.read_text(encoding="utf-8"))
        doc["alumnus"] = "someone-else"
        other.write_text(json.dumps(doc), encoding="utf-8")
        s = self._run({"S01": {"run.py": PASS_PY}}, scorecard=other)  # dry run: recorded
        self.assertFalse(s["scorecard"]["alumnus_is_candidate"])
        with self.assertRaises(rc.RunRefused) as cm:  # live: refused
            self._run(None, repo=self.root / "pack", scorecard=other, dry_run=False, mock=False,
                      seats=[NeverCalledSeat(x) for x in QUORUM.voting_seats])
        self.assertIn("the scorecard is of 'someone-else'", str(cm.exception))

    def test_without_the_rule_in_the_file_the_record_has_no_expiry_block(self):
        seats, _ = crafted_session()
        no_p3 = {**COUNCIL, "rules": [r for r in COUNCIL["rules"] if r["id"] != "P3"]}
        dec = build_decision_record(seats[0]["session"], seats[0]["candidate"], seats, QUORUM, bundle_sha256=None, council=no_p3)
        self.assertEqual((dec["certified_until"], dec["diploma_rule"], dec["scorecard"], dec["admission"]), (None, None, None, None))


# ======================================================================================================
# P3 — the Registry row shows status and expiry
# ======================================================================================================

class RegistryStatus(_Run):
    def _rows(self, seats, decision, *, today, cards=None, include_mock=False):
        td = self.root / f"ledger-{len(list(self.root.iterdir()))}"
        write_session(td, self.signer, seats, decision)
        rows, rejected = registry.build([td], self.signer.public_key, COUNCIL, include_mock=include_mock, today=today,
                                        scorecards=cards)
        self.assertEqual(rejected, [])
        return rows

    def test_certified_row_shows_status_and_expiry(self):
        card = blind_card()
        rows = self._rows(*crafted_session(card=card), today=day(10), cards=as_raw(card))
        row = rows[0]
        self.assertEqual((row.status.status, row.status.certified_until, row.executor), ("certified", date(2026, 12, 30), "ran"))
        md = registry.to_markdown(rows, COUNCIL)
        header = next(ln for ln in md.splitlines() if ln.startswith("| # |"))
        self.assertIn("| Vetoes | Status | Certified until | Provenance |", header)
        line = next(ln for ln in md.splitlines() if ln.startswith("| ") and "Synthetic Pack" in ln)
        self.assertIn("| certified | 2026-12-30 | Council v2 session, signed at run |", line)
        self.assertIn("Status as of 2026-10-11", md)
        self.assertIn("rule P3 (Rector, 2026-09-30): valid 90 days from the signed verdict (P3.1), last valid blind run not "
                      "older than 30 days (P3.2), never-event threshold 1 (P3.3)", md)
        h = registry.to_html(rows, COUNCIL)
        self.assertIn("<th>Status</th><th>Certified until</th><th>Provenance</th>", h)
        self.assertIn("<td>certified</td><td>2026-12-30</td>", h)
        self.assertIn('<tr class="outcome-pass" data-slug="pack">', h)

    def test_the_same_records_lapse_when_the_day_moves(self):
        card = blind_card()
        session = crafted_session(card=card)
        self.assertEqual(self._rows(*session, today=day(29), cards=as_raw(card))[0].status.status, "certified")
        lapsed = self._rows(*session, today=day(30), cards=as_raw(card))  # the blind run is 31 days old
        self.assertEqual((lapsed[0].status.status, lapsed[0].status.conditions), ("lapsed", ("blind_run_too_old",)))
        self.assertIn("| lapsed | 2026-12-30 |", registry.to_markdown(lapsed, COUNCIL))
        fresh = blind_card([a_run(day(-1), 1), a_run(day(30), 2), a_run(day(60), 3), a_run(day(89), 4)])
        self.assertEqual(self._rows(*session, today=day(90), cards=as_raw(fresh))[0].status.status, "certified")
        over = self._rows(*session, today=day(91), cards=as_raw(fresh))
        self.assertEqual((over[0].status.status, over[0].status.conditions), ("lapsed", ("validity_over",)))

    def test_a_never_event_after_the_verdict_puts_the_row_under_review(self):
        card = blind_card()
        session = crafted_session(card=card)
        later = blind_card([a_run(day(-1), 1), a_run(day(5), 2, never=1)])
        rows = self._rows(*session, today=day(6), cards=as_raw(later))
        self.assertEqual(rows[0].status.status, "under-review")
        self.assertIn("| under-review | — |", registry.to_markdown(rows, COUNCIL))

    def test_a_scorecard_with_a_run_removed_is_refused_and_does_not_certify(self):
        three = blind_card([a_run(day(-3), 1), a_run(day(-2), 2, never=1), a_run(day(-1), 3)])
        session = crafted_session(card=three)
        self.assertEqual(self._rows(*session, today=D0, cards=as_raw(three))[0].status.status, "certified")
        trimmed = blind_card([a_run(day(-3), 1), a_run(day(-1), 3)])  # valid on its own; one run short of the signed one
        rows = self._rows(*session, today=D0, cards=as_raw(trimmed))
        self.assertEqual(rows[0].status.status, "lapsed")
        self.assertTrue(any("runs-removed" in n for n in rows[0].notes))
        self.assertIn("runs-removed", registry.to_markdown(rows, COUNCIL))

    def test_an_executor_veto_is_under_review(self):
        failing = {"executor": "ran", "counts": {"scenarios_found": 2, "passed": 1, "failed": 1, "errors": 0, "timeouts": 0},
                   "not_passed": [{"scenario_id": "S02", "status": "fail"}], "error": None}
        card = blind_card()
        rows = self._rows(*crafted_session(card=card, executor=failing), today=D0, cards=as_raw(card))
        self.assertEqual((rows[0].decision.outcome, rows[0].status.status, rows[0].status.conditions),
                         ("VETO", "under-review", ("executor_veto",)))

    def test_a_record_that_says_executor_not_run_shows_it_in_plain_words_and_is_never_certified(self):
        card = blind_card()
        seats, dec = crafted_session(card=card, executor=NOT_RUN)  # not mock, not a dry run, outcome PASS
        self.assertEqual(dec["decision"]["outcome"], "PASS")
        rows = self._rows(seats, dec, today=D0, cards=as_raw(card))
        row = rows[0]
        self.assertEqual((row.executor, row.status.status), ("not run", "evidence-pending"))
        self.assertIn("executor: not run", row.status.reasons[0])
        for text in (registry.to_markdown(rows, COUNCIL), registry.to_html(rows, COUNCIL)):
            line = next(ln for ln in text.splitlines() if "Synthetic Pack" in ln and ("<tr" in ln or ln.startswith("| ")))
            self.assertIn("executor: not run", line)
            self.assertNotIn("certified", line.replace("Certified until", ""))
        for n in (0, 29, 90, 400):
            self.assertNotEqual(self._rows(seats, dec, today=day(n), cards=as_raw(card))[0].status.status, "certified")
        # the row says it even when no date is given and the status columns are absent
        td = self.root / "no-date"
        write_session(td, self.signer, seats, dec)
        plain, _ = registry.build([td], self.signer.public_key, COUNCIL)
        self.assertIn("Council v2 session, signed at run · executor: not run", registry.to_markdown(plain, COUNCIL))

    def test_dry_run_without_executor_pipeline_row(self):
        s = self._run({"S01": {"run.py": PASS_PY}}, run_executor=False, scorecard=self._card_file(), marker=MARKER)
        self.assertEqual(s["decision"]["outcome"], "PASS")
        self.assertIsNone(s["certified_until"])
        self.assertTrue(any("executor: not run" in w for w in s["diploma_rule"]["not_certified_because"]))
        cards, _ = scorecard.load_dir(self.root)
        rows, _ = registry.build([s["out"]], self.signer.public_key, COUNCIL, include_mock=True, today=D0, scorecards=cards)
        self.assertEqual(rows[0].status.status, "evidence-pending")
        self.assertIn(MARKER + " · executor: not run", rows[0].provenance)

    def test_mock_rows_keep_their_marker_and_never_read_as_certified(self):
        s = self._run({"S01": {"run.py": PASS_PY}}, scorecard=self._card_file(), marker=MARKER)
        self.assertEqual(s["decision"]["outcome"], "PASS")
        cards, _ = scorecard.load_dir(self.root)
        for today in (D0, day(45), day(200)):
            rows, _ = registry.build([s["out"]], self.signer.public_key, COUNCIL, include_mock=True, today=today, scorecards=cards)
            row = rows[0]
            self.assertTrue(row.mock)
            self.assertEqual((row.status.status, row.status.clause_id), ("evidence-pending", "P3.c"))
            self.assertIn(MARKER, row.provenance)
            md = registry.to_markdown(rows, COUNCIL)
            self.assertTrue(any(ln.startswith("> **") and MARKER in ln for ln in md.splitlines()))
            self.assertIn("| evidence-pending | — | " + registry.MOCK_PROVENANCE, md)
            self.assertIn('class="outcome-pass registry-mock"', registry.to_html(rows, COUNCIL))
        rows, _ = registry.build([s["out"]], self.signer.public_key, COUNCIL, today=D0, scorecards=cards)
        self.assertEqual(rows, [])  # still excluded by default

    def test_mock_row_with_an_executor_veto_is_under_review(self):
        s = self._run({"S01": {"run.py": FAIL_PY}}, marker=MARKER)
        rows, _ = registry.build([s["out"]], self.signer.public_key, COUNCIL, include_mock=True, today=D0)
        self.assertEqual((rows[0].decision.outcome, rows[0].status.status), ("VETO", "under-review"))
        self.assertIn(MARKER, rows[0].provenance)

    def test_no_date_no_status_columns(self):
        card = blind_card()
        td = self.root / "ledger"
        write_session(td, self.signer, *crafted_session(card=card))
        rows, _ = registry.build([td], self.signer.public_key, COUNCIL)
        self.assertIsNone(rows[0].status)
        self.assertNotIn("Status", registry.to_markdown(rows, COUNCIL))
        self.assertNotIn("Certified until", registry.to_html(rows, COUNCIL))


# ======================================================================================================
# Backward compatibility
# ======================================================================================================

BEFORE = FIXTURES / "signed_before_p3"  # one rehearsal session signed at faculty commit 5a9f369, before rules P3 / P4


class RecordsSignedBeforeThisChange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pub = load_public_key(BEFORE / "TEST-REHEARSAL-council-v2.pub")
        cls.recs, cls.rejected = load_records([BEFORE], cls.pub)

    def test_they_still_verify(self):
        self.assertEqual(self.rejected, [])
        self.assertEqual(sorted(r["_file"] for r in self.recs),
                         ["fixture__DECISION.json", "fixture__anthropic.json", "fixture__executor.json", "fixture__longctx.json",
                          "fixture__reasoning.json", "fixture__velocity.json"])
        dec = next(r for r in self.recs if r["schema"] == DECISION_SCHEMA)
        self.assertEqual(dec["session"]["faculty_commit"], "5a9f369afa662b923b93673b3c3d10f5b6b75b0b")
        for key in ("certified_until", "scorecard", "admission", "diploma_rule"):
            self.assertNotIn(key, dec)  # the old shape, untouched
        raw = json.loads((BEFORE / "fixture__DECISION.json").read_text(encoding="utf-8"))
        self.assertTrue(verify_record(raw, self.pub).ok)
        raw["decision"]["outcome"] = "VETO"
        self.assertFalse(verify_record(raw, self.pub).ok)

    def test_the_registry_row_is_what_it_was(self):
        rows = registry.build_rows(self.recs, COUNCIL, include_mock=True)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row.slug, row.decision.outcome, row.decision.tally, row.decision.vetoes), ("fixture", "PASS", "4/4", {}))
        dec = next(r for r in self.recs if r["schema"] == DECISION_SCHEMA)
        self.assertEqual(json.loads(json.dumps(row.decision.to_dict())), dec["decision"])  # same as signed on 2026-09-30
        self.assertEqual(row.provenance, registry.MOCK_PROVENANCE + " · " + MARKER)
        self.assertIsNone(row.status)
        self.assertNotIn("Status", registry.to_markdown(rows, COUNCIL))
        self.assertEqual(registry.build_rows(self.recs, COUNCIL), [])

    def test_a_status_can_be_derived_for_them(self):
        rows = registry.build_rows(self.recs, COUNCIL, include_mock=True, today=D0)
        s = rows[0].status
        self.assertEqual((s.status, s.clause_id), ("evidence-pending", "P3.c"))  # a pack (4 scenarios), a mock session
        self.assertIn("mock", s.reasons[0])
        dec = next(r for r in self.recs if r["schema"] == DECISION_SCHEMA)
        v = scorecard.Verdict.from_decision_record(dec)
        self.assertEqual((v.outcome, v.executor, v.mock, v.dry_run, v.scorecard_sha256), ("PASS", "ran", True, True, None))


class LegacyOutcomesUnchanged(unittest.TestCase):
    """The 2026 JSON: same outcomes as before P3 / P4, and the alumni without a pack are profile-attested."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.signer = Ed25519Signer.generate("test")
        lmap = registry.legacy_map(COUNCIL)
        for cohort in ("cohort-phase-0", "cohort-q2-2026"):
            for r in legacy_records(FACULTY, cohort, v2_seat_map=lmap):
                write_signed(r, Path(cls.tmp.name) / cohort / f"{r['candidate']['slug']}__{r['seat']['legacy_seat_id']}.json",
                             cls.signer)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _build(self, council, **kw):
        rows, rejected = registry.build([self.tmp.name], self.signer.public_key, council, **kw)
        self.assertEqual(rejected, [])
        return rows

    def test_rows_are_identical_with_and_without_the_new_rules(self):
        only_ex1 = {**COUNCIL, "rules": [r for r in COUNCIL["rules"] if r["id"] == "EX-1"]}
        no_rules = {k: v for k, v in COUNCIL.items() if k != "rules"}
        now_rows = self._build(COUNCIL)
        self.assertTrue(now_rows)
        for older in (only_ex1, no_rules):
            rows = self._build(older)
            self.assertEqual([(r.slug, r.decision.to_dict(), r.seats, r.provenance, r.notes) for r in now_rows],
                             [(r.slug, r.decision.to_dict(), r.seats, r.provenance, r.notes) for r in rows])
            self.assertEqual(registry.to_markdown(now_rows, COUNCIL), registry.to_markdown(rows, older))
            self.assertEqual(registry.to_html(now_rows, COUNCIL), registry.to_html(rows, older))

    def test_a_date_adds_the_status_and_changes_no_outcome(self):
        plain = self._build(COUNCIL)
        dated = self._build(COUNCIL, today=D0)
        self.assertEqual([(r.slug, r.decision.to_dict(), r.seats) for r in plain],
                         [(r.slug, r.decision.to_dict(), r.seats) for r in dated])
        self.assertEqual({r.status.status for r in dated}, {"profile-attested"})  # no pack: admitted on profile
        self.assertTrue(all(r.status.certified_until is None and r.executor is None for r in dated))
        md = registry.to_markdown(dated, COUNCIL)
        self.assertEqual(md.count("| profile-attested | — | legacy 2026 JSON, re-scored by code (origin unsigned) |"), len(dated))
        self.assertNotIn("| certified |", md)

    def test_a_legacy_alumnus_with_a_measured_pack_is_evidence_pending(self):
        slug = self._build(COUNCIL)[0].slug
        doc = a_card([a_run(day(-1), 1)], alumnus=slug)
        cards = {slug: scorecard.RawScorecard(data=doc, sha256="d" * 64, source=f"{slug}.scorecard.json")}
        dated = {r.slug: r.status.status for r in self._build(COUNCIL, today=D0, scorecards=cards)}
        self.assertEqual(dated[slug], "evidence-pending")
        self.assertEqual({v for k, v in dated.items() if k != slug}, {"profile-attested"})


if __name__ == "__main__":
    unittest.main()
