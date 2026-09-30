"""Rule P3 (Rector, 2026-09-30): "the diploma is a blind number that expires".

Three layers, all offline and synthetic:

* the rule is read from ``council/council.json`` (ids, approvals, the three parameters, the ordered statuses);
* the scorecard validator (``council_v2/scorecard.py`` + ``scorecard.schema.json``) and each of its refusals;
* ``derive_status``: every status, and every transition on its boundary day.
"""

import copy
import importlib.util
import inspect
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from council_v2 import registry, rules, scorecard
from council_v2.scorecard import (CERTIFIED, EVIDENCE_PENDING, LAPSED, PROFILE_ATTESTED, UNDER_REVIEW, ScorecardRefused,
                                  Verdict, derive_status)
from tests.helpers import FACULTY

COUNCIL = registry.load_council(FACULTY / "council" / "council.json")
RULE = rules.DiplomaRule.from_council(COUNCIL)
APPROVED = "Rector, 2026-09-30"
D0 = date(2026, 10, 1)  # the day of the signed verdict in these tests
DIGEST = "c" * 64


def day(n: int) -> date:
    return D0 + timedelta(days=n)


def ts(d: date, hh: int = 12) -> str:
    return f"{d.isoformat()}T{hh:02d}:00:00Z"


def a_run(d: date, seed: int, kind: str = "out-of-pool", never: int = 0, by: str = "evaluator", hh: int = 12) -> dict:
    return {"run_at_utc": ts(d, hh), "seed": seed, "kind": kind, "kind_note": "synthetic", "run_by": by, "n": 250,
            "abstained": 3, "never_events": never, "metrics": {"deadline_exact": 0.9}, "expected_answers_sha256_prefix": None}


def a_card(runs: list[dict], **over) -> dict:
    """A scorecard with the shape of the contract file; ``headline_run`` is the last out-of-pool run."""
    blind = [i for i, r in enumerate(runs) if r.get("kind") == "out-of-pool"]
    doc = {"schema": "aetherneum-scorecard/0.1-draft", "alumnus": "tiny-pack", "alumnus_nature": "synthetic AI agent, not a person",
           "status": "evidence-pending", "pack_version": "1.0", "freeze_tag": "v1.0-freeze", "freeze_commit": "a" * 40,
           "written_by": "evaluator (test session), not the builder", "written_at_utc": ts(D0), "certified_until": None,
           "headline_run": blind[-1] if blind else None, "never_event_definition": "a committed value that is wrong",
           "limits": "Synthetic corpus.", "runs": runs}
    doc.update(over)
    return doc


def accepted(runs: list[dict], rule: rules.DiplomaRule = RULE, **over) -> scorecard.Scorecard:
    return scorecard.validate(a_card(runs, **over), rule, sha256=DIGEST)


def verdict(d: date = D0, **over) -> Verdict:
    kw = dict(outcome="PASS", signed_at=scorecard.parse_utc(ts(d)), executor=rules.RAN, mock=False, dry_run=False,
              scorecard_sha256=DIGEST)
    kw.update(over)
    return Verdict(**kw)


def status(*, pack=True, v=None, card=None, today=D0, rule=RULE, veto=False) -> scorecard.Status:
    return derive_status(pack=pack, verdict=v, scorecard=card, today=today, rule=rule, executor_veto=veto)


def codes(doc, **kw) -> list[str]:
    return [r.code for r in scorecard.check(doc, RULE, **kw)]


class RuleIsReadFromTheFile(unittest.TestCase):
    """R7: parameters and statuses are written in council.json; the code extracts them."""

    def test_parameters_as_written_with_ids_and_approval(self):
        rule = next(r for r in COUNCIL["rules"] if r["id"] == "P3")
        self.assertEqual((rule["subject"], rule["approved"], rule["text"]),
                         ("diploma", APPROVED, "the diploma is a blind number that expires"))
        self.assertEqual([(p["id"], p["name"], p["value"], p["approved"]) for p in rule["parameters"]],
                         [("P3.1", "validity_days", 90, APPROVED), ("P3.2", "max_days_between_blind_runs", 30, APPROVED),
                          ("P3.3", "never_event_threshold", 1, APPROVED)])
        self.assertEqual((RULE.rule_id, RULE.approved), ("P3", APPROVED))
        self.assertEqual((RULE.validity_days, RULE.max_days_between_blind_runs, RULE.never_event_threshold), (90, 30, 1))
        self.assertEqual(RULE.parameters()["validity_days"], {"id": "P3.1", "value": 90, "approved": APPROVED})

    def test_statuses_are_an_ordered_list(self):
        self.assertEqual([(i, s) for i, s, _ in RULE.statuses],
                         [("P3.a", PROFILE_ATTESTED), ("P3.b", UNDER_REVIEW), ("P3.c", EVIDENCE_PENDING), ("P3.d", LAPSED),
                          ("P3.e", CERTIFIED)])
        self.assertEqual(sorted(s for _, s, _ in RULE.statuses), sorted(rules.STATUSES))

    def test_the_executor_rule_is_still_the_first_rule(self):
        self.assertEqual([r["id"] for r in COUNCIL["rules"]], ["EX-1", "P3", "P4"])
        self.assertEqual(rules.ExecutorRule.from_council(COUNCIL).rule_id, "EX-1")

    def test_changing_the_file_changes_the_behaviour(self):
        edited = copy.deepcopy(COUNCIL)
        p3 = next(r for r in edited["rules"] if r["id"] == "P3")
        p3["parameters"][0]["value"] = 10
        rule10 = rules.DiplomaRule.from_council(edited)
        self.assertEqual(rule10.certified_until(D0), day(10))
        card = accepted([a_run(day(11), 1)])
        self.assertEqual(status(v=verdict(), card=card, today=day(11)).status, CERTIFIED)
        self.assertEqual(status(v=verdict(), card=card, today=day(11), rule=rule10).status, LAPSED)
        no_p3 = {**COUNCIL, "rules": [r for r in COUNCIL["rules"] if r["id"] != "P3"]}
        self.assertIsNone(rules.DiplomaRule.from_council(no_p3))

    def test_the_order_of_the_statuses_is_the_file_s(self):
        # validity over AND a never-event in the headline run: the file says under-review comes first
        card = accepted([a_run(day(95), 1, never=1)])
        self.assertEqual(status(v=verdict(), card=card, today=day(100)).status, UNDER_REVIEW)
        edited = copy.deepcopy(COUNCIL)
        p3 = next(r for r in edited["rules"] if r["id"] == "P3")
        p3["statuses"] = [p3["statuses"][i] for i in (0, 3, 1, 2, 4)]  # lapsed moved above under-review
        swapped = rules.DiplomaRule.from_council(edited)
        self.assertEqual(status(v=verdict(), card=card, today=day(100), rule=swapped).status, LAPSED)

    def test_a_rule_the_code_cannot_apply_is_an_error_not_ignored(self):
        def edited(fn):
            c = copy.deepcopy(COUNCIL)
            fn(next(r for r in c["rules"] if r["id"] == "P3"))
            return c
        broken = [
            lambda r: r["parameters"].pop(),  # a parameter missing
            lambda r: r["parameters"][0].update(value="ninety"),
            lambda r: r["parameters"][0].update(value=0),
            lambda r: r["parameters"][1].pop("approved"),  # a parameter nobody approved
            lambda r: r["parameters"].append({"id": "P3.9", "name": "grace_days", "value": 5, "approved": APPROVED}),
            lambda r: r["statuses"][1]["when"].append("phase_of_the_moon"),
            lambda r: r["statuses"][0].update(status="graduated"),
            lambda r: r["scorecard"].update(headline_run="best-run"),  # never the best
            lambda r: r["scorecard"].update(blind_run_kind="in-pool"),
            lambda r: r["not_a_signed_verdict"].remove("executor_not_run"),  # 'executor: not run' must never certify
            lambda r: r["not_a_signed_verdict"].remove("mock"),
        ]
        for fn in broken:
            with self.assertRaises(rules.RuleError):
                rules.DiplomaRule.from_council(edited(fn))

    def test_schema_file_and_rule_agree(self):
        schema = scorecard.load_schema()
        rule = next(r for r in COUNCIL["rules"] if r["id"] == "P3")
        self.assertEqual(rule["scorecard"]["schema_file"], "council_v2/scorecard.schema.json")
        self.assertTrue((FACULTY / rule["scorecard"]["schema_file"]).is_file())
        self.assertEqual(schema["properties"]["schema"]["const"], RULE.schema_id)
        self.assertEqual(schema["properties"]["runs"]["items"]["properties"]["kind"]["enum"], list(RULE.run_kinds))
        self.assertEqual(sorted(schema["properties"]["status"]["enum"]), sorted(rules.STATUSES))
        edited = copy.deepcopy(COUNCIL)
        next(r for r in edited["rules"] if r["id"] == "P3")["scorecard"]["run_kinds"].append("showcase")
        with self.assertRaises(rules.RuleError):  # the rule and the schema file must say the same thing
            scorecard.check(a_card([a_run(D0, 1)]), rules.DiplomaRule.from_council(edited))

    @unittest.skipUnless(importlib.util.find_spec("jsonschema"), "jsonschema not installed")
    def test_schema_file_is_a_valid_json_schema_and_agrees_with_the_validator(self):
        import jsonschema
        schema = scorecard.load_schema()
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        good = a_card([a_run(D0, 1, kind="protocol"), a_run(day(1), 2)])
        self.assertEqual(list(validator.iter_errors(good)), [])
        self.assertEqual(scorecard.schema_errors(good, schema), [])
        for bad in (a_card([a_run(D0, 1, kind="showcase")]), a_card([]), {k: v for k, v in good.items() if k != "limits"},
                    a_card([a_run(D0, 1)], freeze_commit="not-a-sha"), a_card([{**a_run(D0, 1), "never_events": -1}])):
            self.assertTrue(list(validator.iter_errors(bad)))
            self.assertTrue(scorecard.schema_errors(bad, schema))


class Validator(unittest.TestCase):
    def test_a_scorecard_with_the_contract_shape_is_accepted(self):
        # the shape of the first scorecard written for an alumnus: two protocol runs, then two out-of-pool runs
        runs = [a_run(D0, 20261005, "protocol", hh=15), a_run(D0, 20261006, "protocol", hh=16),
                a_run(D0, 20261007, hh=17), a_run(D0, 20261008, hh=18)]
        card = scorecard.validate(a_card(runs), RULE)
        self.assertEqual((len(card.runs), card.headline.index, card.headline.kind), (4, 3, "out-of-pool"))
        self.assertEqual(card.alumnus, "tiny-pack")
        s = card.summary()
        self.assertEqual((s["runs"], s["headline_run"], len(s["run_digests"])), (4, 3, 4))
        self.assertEqual(codes(a_card(runs)), [])

    def test_every_required_field_is_required(self):
        good = a_card([a_run(D0, 1)])
        for key in ("schema", "alumnus", "pack_version", "freeze_tag", "freeze_commit", "written_by", "headline_run",
                    "limits", "runs"):
            doc = {k: v for k, v in good.items() if k != key}
            self.assertEqual(codes(doc), ["required-field"], key)
        for key in ("run_at_utc", "seed", "kind", "run_by", "n", "abstained", "never_events", "metrics"):
            doc = a_card([{k: v for k, v in a_run(D0, 1).items() if k != key}])
            self.assertEqual(codes(doc), ["required-field"], key)
        with self.assertRaises(ScorecardRefused) as cm:
            scorecard.validate({k: v for k, v in good.items() if k != "limits"}, RULE)
        self.assertIn("P3", str(cm.exception))
        self.assertIn("'limits'", str(cm.exception))

    def test_shape_refusals(self):
        self.assertEqual(codes([]), ["schema"])
        self.assertEqual(codes(a_card([])), ["schema"])  # a scorecard with no run measures nothing
        self.assertEqual(codes(a_card([a_run(D0, 1)], schema="aetherneum-scorecard/9")), ["schema"])
        self.assertEqual(codes(a_card([a_run(D0, 1)], freeze_commit="80f95db")), ["schema"])  # a full commit id
        self.assertEqual(codes(a_card([{**a_run(D0, 1), "never_events": True}])), ["schema"])
        self.assertEqual(codes(a_card([{**a_run(D0, 1), "run_at_utc": "2026-13-40T12:00:00Z"}])), ["run-date"])
        self.assertEqual(codes(a_card([{**a_run(D0, 1), "run_at_utc": "30 September 2026"}])), ["schema"])

    def test_run_kinds_are_protocol_or_out_of_pool(self):
        self.assertEqual(codes(a_card([a_run(D0, 1, kind="showcase")], headline_run=None)), ["run-kind"])
        self.assertEqual(codes(a_card([a_run(D0, 1, kind="protocol")])), [])
        self.assertEqual(codes(a_card([a_run(D0, 1, kind="out-of-pool")])), [])

    def test_runs_must_be_in_date_order(self):
        doc = a_card([a_run(day(2), 1), a_run(day(1), 2)])
        self.assertEqual(codes(doc), ["run-order"])
        self.assertEqual(codes(a_card([a_run(D0, 1, hh=9), a_run(D0, 2, hh=9)])), [])  # same instant: still in order

    def test_headline_run_is_the_last_out_of_pool_run_never_the_best(self):
        runs = [a_run(day(0), 1), a_run(day(1), 2, "protocol"), a_run(day(2), 3), a_run(day(3), 4, "protocol")]
        runs[0]["metrics"] = {"deadline_exact": 1.0}  # the best blind run is the first one
        runs[2]["metrics"] = {"deadline_exact": 0.7}
        self.assertEqual(scorecard.validate(a_card(runs), RULE).headline.index, 2)
        for wrong in (0, 1, 3, None):
            refusals = scorecard.check(a_card(runs, headline_run=wrong), RULE)
            self.assertEqual([r.code for r in refusals], ["headline-run"], wrong)
            self.assertIn("never the best", refusals[0].message)
        only_protocol = [a_run(D0, 1, "protocol")]
        self.assertIsNone(scorecard.validate(a_card(only_protocol), RULE).headline)
        self.assertEqual(codes(a_card(only_protocol, headline_run=0)), ["headline-run"])

    def test_a_run_by_the_builder_is_refused(self):
        for who in ("builder", "Builder", "the builder", "builder (pack session)"):
            self.assertEqual(codes(a_card([a_run(D0, 1, by=who)])), ["run-by-builder"], who)
        for who in ("evaluator", "evaluator, not the builder", "executor seat"):
            self.assertEqual(codes(a_card([a_run(D0, 1, by=who)])), [], who)
        named = a_card([a_run(D0, 1, by="Pack Session 7")], builder="pack session 7")
        self.assertEqual(codes(named), ["run-by-builder"])  # the scorecard names its builder: no run by that name
        self.assertEqual(codes(a_card([a_run(D0, 1)], written_by="builder")), ["written-by-builder"])

    def test_a_seed_is_used_once(self):
        self.assertEqual(codes(a_card([a_run(day(0), 7), a_run(day(1), 7)])), ["seed-reused"])

    def test_every_run_is_kept(self):
        three = [a_run(day(0), 1), a_run(day(1), 2, never=1), a_run(day(2), 3)]
        signed = scorecard.validate(a_card(three), RULE).summary()  # what a decision record signs
        self.assertEqual(codes(a_card(three), previous=signed), [])
        self.assertEqual(codes(a_card(three + [a_run(day(3), 4)]), previous=signed), [])  # runs are only ever added
        dropped = a_card([three[0], three[2]])  # the unfavourable run removed
        refusals = scorecard.check(dropped, RULE, previous=signed)
        self.assertEqual([r.code for r in refusals], ["runs-removed", "runs-removed"])
        self.assertIn("2 run(s) listed, the previous signed version had 3", refusals[0].message)
        self.assertIn("seed 2", refusals[1].message)
        with self.assertRaises(ScorecardRefused):
            scorecard.validate(dropped, RULE, previous=signed)
        cleaned = copy.deepcopy(three)
        cleaned[1]["never_events"] = 0  # same number of runs, one rewritten
        self.assertEqual(codes(a_card(cleaned), previous=signed), ["runs-removed"])
        # a whole previous scorecard, or only its number of runs, can be given as the previous version
        self.assertEqual(codes(dropped, previous=a_card(three)), ["runs-removed", "runs-removed"])
        self.assertEqual(codes(dropped, previous={"runs": 3}), ["runs-removed"])
        self.assertEqual(codes(a_card(three), previous={"runs": 3}), [])

    def test_load_reads_utf8_and_digests_the_file_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "tiny-pack.scorecard.json"
            raw = json.dumps(a_card([a_run(D0, 1)], limits="Synthetic corpus — è tutto."), ensure_ascii=False, indent=1).encode("utf-8")
            p.write_bytes(raw)
            card = scorecard.load(p, RULE)
            self.assertEqual((card.sha256, card.source), (scorecard.sha256_bytes(raw), "tiny-pack.scorecard.json"))
            self.assertEqual(card.summary()["sha256"], scorecard.sha256_bytes(raw))
            (Path(td) / "broken.scorecard.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(ScorecardRefused) as cm:
                scorecard.load(Path(td) / "broken.scorecard.json", RULE)
            self.assertEqual(cm.exception.codes, ["unreadable"])
            found, notes = scorecard.load_dir(td)
            self.assertEqual(sorted(found), ["tiny-pack"])
            self.assertEqual(len(notes), 1)

    def test_a_schema_keyword_the_validator_does_not_apply_is_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.json"
            p.write_text(json.dumps({"type": "object", "properties": {"x": {"maxLength": 3}}}), encoding="utf-8")
            with self.assertRaises(rules.RuleError):
                scorecard.load_schema(p)


class StatusTransitions(unittest.TestCase):
    """One test per status and per boundary.  The verdict is signed on D0 = 2026-10-01."""

    def test_no_pack_is_profile_attested(self):
        s = status(pack=False)
        self.assertEqual((s.status, s.clause_id, s.conditions), (PROFILE_ATTESTED, "P3.a", ("no_pack",)))
        self.assertEqual((s.rule_id, s.approved), ("P3", APPROVED))
        self.assertIsNone(s.certified_until)
        self.assertEqual(status(pack=False, veto=True).status, PROFILE_ATTESTED)  # nothing to veto without a pack

    def test_measured_pack_without_a_signed_verdict_is_evidence_pending(self):
        s = status(card=accepted([a_run(D0, 1)]))
        self.assertEqual((s.status, s.clause_id, s.reasons), (EVIDENCE_PENDING, "P3.c", ("no signed verdict",)))
        unmeasured = status()  # a pack, no scorecard yet
        self.assertEqual(unmeasured.status, EVIDENCE_PENDING)
        self.assertIn("no accepted scorecard: the pack is not measured", unmeasured.notes)

    def test_certified(self):
        s = status(v=verdict(), card=accepted([a_run(day(-1), 1)]))
        self.assertEqual((s.status, s.clause_id), (CERTIFIED, "P3.e"))
        self.assertEqual(s.certified_until, date(2026, 12, 30))  # 2026-10-01 + 90 days
        self.assertEqual((s.last_blind_run, s.blind_run_due), (day(-1), day(29)))
        self.assertEqual(s.headline_run, 0)
        self.assertEqual(s.to_dict()["certified_until"], "2026-12-30")

    def test_validity_day_90_is_the_last_certified_day(self):
        card = accepted([a_run(day(-1), 1), a_run(day(29), 2), a_run(day(59), 3), a_run(day(89), 4)])
        self.assertEqual(status(v=verdict(), card=card, today=day(89)).status, CERTIFIED)
        self.assertEqual(status(v=verdict(), card=card, today=day(90)).status, CERTIFIED)
        after = status(v=verdict(), card=card, today=day(91))
        self.assertEqual((after.status, after.clause_id, after.conditions), (LAPSED, "P3.d", ("validity_over",)))
        self.assertEqual(after.certified_until, day(90))
        self.assertIn("validity over", after.reasons[0])

    def test_blind_run_day_30_is_the_last_certified_day(self):
        card = accepted([a_run(day(-1), 1)])
        self.assertEqual(status(v=verdict(), card=card, today=day(28)).status, CERTIFIED)
        self.assertEqual(status(v=verdict(), card=card, today=day(29)).status, CERTIFIED)  # the run is 30 days old
        late = status(v=verdict(), card=card, today=day(30))  # 31 days old
        self.assertEqual((late.status, late.conditions), (LAPSED, ("blind_run_too_old",)))
        self.assertIn("31 days old; maximum 30", late.reasons[0])
        # a new valid blind run brings the diploma back; a protocol run does not
        self.assertEqual(status(v=verdict(), card=accepted([a_run(day(-1), 1), a_run(day(30), 2, "protocol")]),
                                today=day(30)).status, LAPSED)
        self.assertEqual(status(v=verdict(), card=accepted([a_run(day(-1), 1), a_run(day(30), 2)]), today=day(30)).status,
                         CERTIFIED)

    def test_a_verdict_without_a_blind_run_does_not_certify(self):
        none = status(v=verdict())  # no scorecard at all
        self.assertEqual((none.status, none.conditions, none.reasons), (LAPSED, ("blind_run_too_old",),
                                                                        ("no valid blind run on the scorecard",)))
        self.assertEqual(status(v=verdict(), card=accepted([a_run(day(-1), 1, "protocol")])).status, LAPSED)

    def test_one_never_event_in_the_headline_run_is_under_review(self):
        card = accepted([a_run(day(-2), 1), a_run(day(-1), 2, never=1)])
        s = status(v=verdict(), card=card)
        self.assertEqual((s.status, s.clause_id, s.conditions), (UNDER_REVIEW, "P3.b", ("never_event_in_headline_run",)))
        self.assertIn("1 never-event(s); threshold 1", s.reasons[0])
        self.assertEqual(status(card=card).status, UNDER_REVIEW)  # with or without a signed verdict
        # a later clean blind run becomes the headline run; the old never-event predates the verdict
        cleared = accepted([a_run(day(-3), 1), a_run(day(-2), 2, never=1), a_run(day(-1), 3)])
        self.assertEqual(status(v=verdict(), card=cleared).status, CERTIFIED)

    def test_one_never_event_in_any_run_after_the_verdict_is_under_review_until_a_new_defence(self):
        card = accepted([a_run(day(-1), 1), a_run(day(5), 2, "protocol", never=1), a_run(day(10), 3)])
        s = status(v=verdict(), card=card, today=day(12))
        self.assertEqual((s.status, s.conditions), (UNDER_REVIEW, ("never_event_after_verdict",)))
        self.assertIn("runs[1]", s.reasons[0])
        self.assertEqual(status(v=verdict(), card=card, today=day(4)).status, UNDER_REVIEW)  # the date is not a filter
        # a new defence: a verdict signed after that run has seen it
        self.assertEqual(status(v=verdict(day(11)), card=card, today=day(12)).status, CERTIFIED)
        # a protocol run with a never-event BEFORE the verdict was in front of the Council: not a trigger
        before = accepted([a_run(day(-3), 1, "protocol", never=2), a_run(day(-1), 2)])
        self.assertEqual(status(v=verdict(), card=before).status, CERTIFIED)

    def test_a_never_event_in_an_earlier_run_with_no_verdict_is_under_review(self):
        # P3.3 "until a new defence": a clean last run does not wash out an earlier never-event before any verdict
        card = accepted([a_run(day(-4), 1, "protocol"), a_run(day(-3), 2, "protocol", never=2),
                         a_run(day(-2), 3, never=1), a_run(day(-1), 4)])
        s = status(card=card)
        self.assertEqual((s.status, s.clause_id, s.conditions), (UNDER_REVIEW, "P3.b", ("never_event_not_defended",)))
        self.assertIn("runs[1]", s.reasons[0])
        self.assertIn("runs[2]", s.reasons[0])
        self.assertEqual(status(card=accepted([a_run(day(-2), 1, "protocol"), a_run(day(-1), 2)])).status, EVIDENCE_PENDING)
        # a verdict signed after those runs is the new defence
        self.assertEqual(status(v=verdict(), card=card).status, CERTIFIED)

    def test_the_never_event_threshold_is_the_file_s(self):
        edited = copy.deepcopy(COUNCIL)
        next(r for r in edited["rules"] if r["id"] == "P3")["parameters"][2]["value"] = 2
        rule2 = rules.DiplomaRule.from_council(edited)
        one = [a_run(day(-1), 1, never=1)]
        self.assertEqual(status(v=verdict(), card=accepted(one)).status, UNDER_REVIEW)
        self.assertEqual(status(v=verdict(), card=accepted(one, rule2), rule=rule2).status, CERTIFIED)
        two = [a_run(day(-1), 1, never=2)]
        self.assertEqual(status(v=verdict(), card=accepted(two, rule2), rule=rule2).status, UNDER_REVIEW)

    def test_executor_veto_is_under_review(self):
        card = accepted([a_run(day(-1), 1)])
        s = status(v=verdict(), card=card, veto=True)
        self.assertEqual((s.status, s.clause_id, s.reasons), (UNDER_REVIEW, "P3.b", ("executor veto (rule EX-1)",)))
        self.assertEqual(status(card=card, veto=True).status, UNDER_REVIEW)
        self.assertEqual(status(veto=True).status, UNDER_REVIEW)

    def test_a_mock_or_dry_run_record_never_certifies(self):
        card = accepted([a_run(day(-1), 1)])
        for kw, word in ((dict(mock=True), "mock"), (dict(dry_run=True), "dry run")):
            s = status(v=verdict(**kw), card=card)
            self.assertEqual((s.status, s.clause_id), (EVIDENCE_PENDING, "P3.c"))
            self.assertIn(word, s.reasons[0])
            self.assertIsNone(s.certified_until)

    def test_a_record_that_says_executor_not_run_never_certifies(self):
        card = accepted([a_run(day(-1), 1)])
        s = status(v=verdict(executor=rules.NOT_RUN), card=card)
        self.assertEqual(s.status, EVIDENCE_PENDING)
        self.assertIn("executor: not run", s.reasons[0])
        self.assertEqual(status(v=verdict(executor=None), card=card).status, EVIDENCE_PENDING)  # no executor result at all
        for today in (D0, day(29), day(90), day(400)):
            self.assertNotEqual(status(v=verdict(executor=rules.NOT_RUN), card=card, today=today).status, CERTIFIED)

    def test_an_outcome_other_than_pass_or_no_scorecard_digest_never_certifies(self):
        card = accepted([a_run(day(-1), 1)])
        for outcome in ("VETO", "FAIL", "NO_QUORUM", None):
            s = status(v=verdict(outcome=outcome), card=card)
            self.assertEqual(s.status, EVIDENCE_PENDING, outcome)
        s = status(v=verdict(scorecard_sha256=None), card=card)
        self.assertEqual((s.status, s.reasons), (EVIDENCE_PENDING, ("the signed record relied on no scorecard",)))

    def test_the_date_is_an_argument_and_nothing_reads_a_clock(self):
        card = accepted([a_run(day(-1), 1)])
        a = status(v=verdict(), card=card, today=day(7)).to_dict()
        b = status(v=verdict(), card=card, today=day(7)).to_dict()
        self.assertEqual(a, b)
        self.assertEqual(a["as_of"], day(7).isoformat())
        for not_a_date in (datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc), "2026-10-08", None):
            with self.assertRaises(TypeError):
                status(v=verdict(), card=card, today=not_a_date)
        source = inspect.getsource(scorecard)
        for clock in ("now(", "today()", "import time", "utcnow"):
            self.assertNotIn(clock, source)

    def test_the_file_s_own_status_field_is_informative_only(self):
        card = accepted([a_run(day(-1), 1)], status="certified")  # the file claims what only a verdict can give
        s = status(card=card)
        self.assertEqual(s.status, EVIDENCE_PENDING)
        self.assertTrue(any("informative" in n for n in s.notes))


if __name__ == "__main__":
    unittest.main()
