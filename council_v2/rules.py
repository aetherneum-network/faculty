"""Council rules that live in ``council/council.json`` and are only *extracted* here.

Operating rule R7: a rule is written once, in an ordered file; the code reads
it.  To change the behaviour, change the file (with the approval it names),
not this module.

Rule EX-1 (Rector decision D19, 2026-09-30), verbatim:
"veto until every declared scenario passes; zero scenarios started counts as
zero artifacts".

How the file is read
--------------------
``council.json["rules"]`` is an ordered list.  The executor rule is the FIRST
entry whose ``subject`` is ``"executor"`` (first wins).  Inside a rule the
``exceptions`` are read before the ``clauses``: the first exception that
matches silences the rule.  Every clause whose condition holds applies.

Condition vocabulary (``when``), deliberately tiny; an unknown key is an
error, never ignored::

    {"executor": "not run"}             the executor did not run
    {"scenarios_found_min": N}          scenarios_found >= N
    {"passed_below_found": true}        passed < scenarios_found
    {"scenarios_started_max": N}        scenarios started <= N
    {"executor_crashed": true}          the executor ran and crashed (clause EX-1.c)

Effects::

    "silent"                            (exceptions) the rule does nothing
    {"outcome": "VETO"}                 the Council outcome is VETO
    {"artifact_count": N}               the evidence caps read artifact_count as N

A scenario is *started* when its process was launched: its status is one of
the clause's ``started_statuses`` (pass, fail, timeout).  Status ``error``
means it could not be launched (no command, containment refusal, OS error).

The signed input of the rule is the *executor summary* (``executor_summary``):
it is written into every seat record and into the decision record, so the
ruling can be recomputed from signed data alone (``record.py``,
``registry.py``).  Records without a summary (the 2026 legacy imports, decoy
calibration records) are outside the rule: ``evaluate`` is never called for
them and their outcomes are unchanged.

Rules P3 and P4 (Rector, 2026-09-30) are extracted the same way:

* ``DiplomaRule`` (subject ``"diploma"``): the three parameters of the diploma
  (each with its own id and approval), the ordered list of statuses (the first
  status with a condition that holds wins) and what the scorecard validator
  needs.  The status itself is derived in ``council_v2/scorecard.py``.
* ``AdmissionRule`` (subject ``"admission"``): a defence starts only for a
  candidate whose pack exists and passes the executor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any, Mapping

NOT_RUN = "not run"
RAN = "ran"
NOTHING_TO_EXECUTE = "no scenarios/ directory: nothing to execute"

# executor status -> the counter that holds it in ExecutorResult / the summary
STATUS_COUNTER = {"pass": "passed", "fail": "failed", "error": "errors", "timeout": "timeouts"}
COUNT_KEYS = ("scenarios_found", "passed", "failed", "errors", "timeouts")
_WHEN_KEYS = {"executor", "scenarios_found_min", "passed_below_found", "scenarios_started_max", "executor_crashed"}
_MAX_LISTED = 12


class RuleError(ValueError):
    """The rules block of council.json cannot be read as written."""


def executor_summary(run_executor: bool, result: Mapping[str, Any] | None, error: str | None = None) -> dict[str, Any]:
    """What the executor did, in the shape the rule reads (and the records sign).

    ``result`` is ``ExecutorResult.to_dict()`` or ``None`` (nothing was executed).
    ``result is None`` together with an ``error`` means the executor itself
    crashed: the summary says ``"crashed": true`` and the number of scenarios
    found is unknown (clause EX-1.c).
    """
    if not run_executor:
        return {"executor": NOT_RUN, "counts": None, "not_passed": [], "error": None}
    if result is None:
        crashed = bool(error) and error != NOTHING_TO_EXECUTE
        summary = {"executor": RAN, "counts": {k: 0 for k in COUNT_KEYS}, "not_passed": [],
                   "error": error or NOTHING_TO_EXECUTE}
        if crashed:
            summary["crashed"] = True
        return summary
    counts = {k: int(result.get(k, 0)) for k in COUNT_KEYS}
    not_passed = [{"scenario_id": r["scenario_id"], "status": r["status"]}
                  for r in result.get("results", []) if r.get("status") != "pass"]
    return {"executor": RAN, "counts": counts, "not_passed": not_passed, "error": error}


@dataclass
class ExecutorRuling:
    """The rule applied to one executor summary."""

    rule_id: str
    approved: str
    text: str
    executor: str  # "ran" | "not run"
    counts: dict[str, int] | None  # scenarios_found, started, passed, failed, errors, timeouts
    fired: bool
    clauses_fired: list[str] = field(default_factory=list)
    veto: bool = False
    zero_artifacts: bool = False
    artifact_count_as: int | None = None
    not_passed: list[dict[str, str]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    veto_short: str | None = None
    veto_reason: str | None = None
    cap_reason: str | None = None
    exception: str | None = None
    crashed: bool = False  # the executor ran and crashed: scenarios found unknown (EX-1.c)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutorRule:
    rule_id: str
    text: str
    approved: str
    exception_id: str | None
    veto_clause_id: str | None
    veto_found_min: int
    veto_outcome: str
    zero_clause_id: str | None
    zero_started_max: int
    zero_artifact_count: int
    started_statuses: tuple[str, ...]
    live_requires_executor: bool
    crash_clause_id: str | None = None
    crash_approved: str | None = None

    # ------------------------------------------------------------------ extraction
    @classmethod
    def from_council(cls, council: Mapping[str, Any] | None) -> "ExecutorRule | None":
        """The first rule with ``subject == "executor"``; ``None`` if the file has none."""
        for rule in (council or {}).get("rules", []) or []:
            if isinstance(rule, Mapping) and rule.get("subject") == "executor":
                return cls._parse(rule)
        return None

    @classmethod
    def _parse(cls, rule: Mapping[str, Any]) -> "ExecutorRule":
        rid = rule.get("id")
        for key in ("id", "text", "approved"):
            if not isinstance(rule.get(key), str) or not rule[key].strip():
                raise RuleError(f"executor rule: missing {key!r}")
        exception_id = None
        for exc in rule.get("exceptions", []) or []:
            when = exc.get("when") or {}
            cls._check_when(rid, when)
            if when == {"executor": NOT_RUN} and exc.get("effect") == "silent":
                exception_id = exception_id or exc.get("id")
            else:
                raise RuleError(f"{rid}: exception {exc.get('id')!r} is not one this code can apply")
        veto_id = zero_id = crash_id = crash_approved = None
        found_min, outcome, started_max, art_count = 1, "VETO", 0, 0
        started: tuple[str, ...] = ("pass", "fail", "timeout")
        for clause in rule.get("clauses", []) or []:
            when, effect = clause.get("when") or {}, clause.get("effect") or {}
            cls._check_when(rid, when)
            if "outcome" in effect and "executor_crashed" in when:
                if crash_id is not None or when != {"executor_crashed": True} or effect != {"outcome": "VETO"}:
                    raise RuleError(f"{rid}: clause {clause.get('id')!r} is not one this code can apply")
                crash_id, crash_approved = clause.get("id"), clause.get("approved") or rule["approved"]
            elif "outcome" in effect and veto_id is None:
                if not when.get("passed_below_found") or effect["outcome"] != "VETO":
                    raise RuleError(f"{rid}: clause {clause.get('id')!r} is not one this code can apply")
                veto_id, found_min, outcome = clause.get("id"), int(when.get("scenarios_found_min", 1)), effect["outcome"]
            elif "artifact_count" in effect and zero_id is None:
                if "scenarios_started_max" not in when:
                    raise RuleError(f"{rid}: clause {clause.get('id')!r} is not one this code can apply")
                zero_id, started_max, art_count = clause.get("id"), int(when["scenarios_started_max"]), int(effect["artifact_count"])
                started = tuple(clause.get("started_statuses") or started)
                unknown = [s for s in started if s not in STATUS_COUNTER]
                if unknown:
                    raise RuleError(f"{rid}: unknown started_statuses {unknown}")
            else:
                raise RuleError(f"{rid}: clause {clause.get('id')!r} has no effect this code can apply")
        return cls(rule_id=rid, text=rule["text"], approved=rule["approved"], exception_id=exception_id,
                   veto_clause_id=veto_id, veto_found_min=found_min, veto_outcome=outcome,
                   zero_clause_id=zero_id, zero_started_max=started_max, zero_artifact_count=art_count,
                   started_statuses=started, live_requires_executor=bool(rule.get("live_requires_executor", False)),
                   crash_clause_id=crash_id, crash_approved=crash_approved)

    @staticmethod
    def _check_when(rid: str, when: Mapping[str, Any]) -> None:
        unknown = sorted(set(when) - _WHEN_KEYS)
        if unknown:
            raise RuleError(f"{rid}: unknown condition(s) {unknown}")

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, summary: Mapping[str, Any]) -> ExecutorRuling:
        base = dict(rule_id=self.rule_id, approved=self.approved, text=self.text)
        if summary.get("executor") == NOT_RUN:
            if self.exception_id is None:
                raise RuleError(f"{self.rule_id}: the executor did not run and the rule has no exception for it")
            return ExecutorRuling(**base, executor=NOT_RUN, counts=None, fired=False, exception=self.exception_id,
                                  reasons=[f"{self.rule_id} silent ({self.exception_id}): executor not run"])
        c = {k: int((summary.get("counts") or {}).get(k, 0)) for k in COUNT_KEYS}
        c["started"] = sum(c[STATUS_COUNTER[s]] for s in self.started_statuses)
        not_passed = [dict(x) for x in summary.get("not_passed") or []]
        ruling = ExecutorRuling(**base, executor=RAN, counts=c, fired=False, not_passed=not_passed,
                                crashed=self.crashed(summary))
        found, passed = c["scenarios_found"], c["passed"]
        if self.veto_clause_id and found >= self.veto_found_min and passed < found:
            ruling.veto = True
            ruling.clauses_fired.append(self.veto_clause_id)
            listed = ", ".join(f"{x['scenario_id']} ({x['status']})" for x in not_passed[:_MAX_LISTED])
            more = f", +{len(not_passed) - _MAX_LISTED} more" if len(not_passed) > _MAX_LISTED else ""
            ruling.veto_short = f"{self.veto_clause_id}: {found - passed} of {found} declared scenarios not passed"
            ruling.veto_reason = (
                f"{self.rule_id} veto ({self.veto_clause_id}, {self.approved}): {found - passed} of {found} declared "
                f"scenario(s) not passed: {listed}{more}")
            ruling.reasons.append(ruling.veto_reason)
        if self.zero_clause_id and c["started"] <= self.zero_started_max:
            ruling.zero_artifacts = True
            ruling.artifact_count_as = self.zero_artifact_count
            ruling.clauses_fired.append(self.zero_clause_id)
            ruling.cap_reason = (f"{self.rule_id} ({self.zero_clause_id}): zero scenarios started ({found} found) "
                                 f"counts as zero artifacts ({self.approved})")
            why = summary.get("error") or (f"{found} found, none could be launched" if found else "none found")
            ruling.reasons.append(
                f"{self.rule_id} ({self.zero_clause_id}, {self.approved}): zero scenarios started ({why}) "
                f"counts as {self.zero_artifact_count} artifacts")
        if self.crash_clause_id and ruling.crashed:
            ruling.veto = True
            ruling.clauses_fired.append(self.crash_clause_id)
            reason = (f"{self.rule_id} veto ({self.crash_clause_id}, {self.crash_approved}): the executor ran and crashed "
                      f"({summary.get('error')}): the number of declared scenarios is unknown, so none is known to pass")
            if ruling.veto_short is None:
                ruling.veto_short = f"{self.crash_clause_id}: the executor crashed, declared scenarios unknown"
                ruling.veto_reason = reason
            ruling.reasons.append(reason)
        ruling.fired = bool(ruling.clauses_fired)
        if not ruling.fired:
            ruling.reasons.append(f"{self.rule_id} silent: {passed} of {found} declared scenario(s) passed")
        return ruling

    @staticmethod
    def crashed(summary: Mapping[str, Any]) -> bool:
        """The executor ran and crashed.  Summaries signed before clause EX-1.c have no ``crashed`` key: for
        them a crash is an ``error`` that is not "nothing to execute" (the only two errors a summary can carry)."""
        if summary.get("executor") != RAN:
            return False
        if "crashed" in summary:
            return bool(summary["crashed"])
        return bool(summary.get("error")) and summary["error"] != NOTHING_TO_EXECUTE


def ruling_for(council: Mapping[str, Any] | None, summary: Mapping[str, Any] | None) -> ExecutorRuling | None:
    """Apply the executor rule of ``council`` to ``summary``; ``None`` when there is no rule or no summary."""
    if summary is None:
        return None
    rule = ExecutorRule.from_council(council)
    return rule.evaluate(summary) if rule else None


# ======================================================================================================
# Rules P3 and P4 (Rector, 2026-09-30)
# ======================================================================================================

def first_rule(council: Mapping[str, Any] | None, subject: str) -> Mapping[str, Any] | None:
    """The first rule of ``council["rules"]`` with this subject (first wins); ``None`` if there is none."""
    for rule in (council or {}).get("rules", []) or []:
        if isinstance(rule, Mapping) and rule.get("subject") == subject:
            return rule
    return None


def _head(rule: Mapping[str, Any], what: str) -> tuple[str, str, str]:
    for key in ("id", "text", "approved"):
        if not isinstance(rule.get(key), str) or not rule[key].strip():
            raise RuleError(f"{what} rule: missing {key!r}")
    return rule["id"], rule["text"], rule["approved"]


# ---- P3: the diploma is a blind number that expires ------------------------------------------------------

DIPLOMA_PARAMETERS = ("validity_days", "max_days_between_blind_runs", "never_event_threshold")
STATUSES = ("profile-attested", "evidence-pending", "certified", "lapsed", "under-review")
STATUS_CONDITIONS = ("no_pack", "executor_veto", "never_event_in_headline_run", "never_event_after_verdict",
                     "never_event_not_defended",
                     "no_signed_verdict", "validity_over", "blind_run_too_old", "otherwise")
NOT_A_VERDICT = ("mock", "dry_run", "executor_not_run", "outcome_not_pass", "no_scorecard_digest")
HEADLINE_LAST_BLIND = "last-blind-run"


@dataclass(frozen=True)
class DiplomaRule:
    """Rule P3 as written in council.json: parameters, ordered statuses, scorecard contract."""

    rule_id: str
    text: str
    approved: str
    validity_days: int
    max_days_between_blind_runs: int
    never_event_threshold: int
    parameter_sources: tuple[tuple[str, str, str], ...]  # (name, id, approved)
    statuses: tuple[tuple[str, str, tuple[str, ...]], ...]  # (id, status, conditions), in file order
    not_a_verdict: tuple[str, ...]
    schema_id: str
    run_kinds: tuple[str, ...]
    blind_run_kind: str
    builder_labels: tuple[str, ...]

    @classmethod
    def from_council(cls, council: Mapping[str, Any] | None) -> "DiplomaRule | None":
        rule = first_rule(council, "diploma")
        return cls._parse(rule) if rule is not None else None

    @classmethod
    def _parse(cls, rule: Mapping[str, Any]) -> "DiplomaRule":
        rid, text, approved = _head(rule, "diploma")
        values: dict[str, int] = {}
        sources = []
        for p in rule.get("parameters", []) or []:
            name = p.get("name")
            if name not in DIPLOMA_PARAMETERS:
                raise RuleError(f"{rid}: unknown parameter {name!r}")
            if name in values:
                raise RuleError(f"{rid}: parameter {name!r} is written twice")
            value = p.get("value")
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise RuleError(f"{rid}: parameter {name!r} must be a whole number >= 1, not {value!r}")
            for key in ("id", "approved"):
                if not isinstance(p.get(key), str) or not p[key].strip():
                    raise RuleError(f"{rid}: parameter {name!r} has no {key!r}")
            values[name] = value
            sources.append((name, p["id"], p["approved"]))
        missing = [n for n in DIPLOMA_PARAMETERS if n not in values]
        if missing:
            raise RuleError(f"{rid}: missing parameter(s) {missing}")
        statuses = []
        for s in rule.get("statuses", []) or []:
            conds = tuple(s.get("when") or ())
            unknown = [c for c in conds if c not in STATUS_CONDITIONS]
            if s.get("status") not in STATUSES or not conds or unknown or not s.get("id"):
                raise RuleError(f"{rid}: status entry {s.get('id')!r} is not one this code can apply "
                                f"(status {s.get('status')!r}, unknown conditions {unknown})")
            statuses.append((s["id"], s["status"], conds))
        if not statuses:
            raise RuleError(f"{rid}: no statuses written")
        not_a_verdict = tuple(rule.get("not_a_signed_verdict") or ())
        unknown = [c for c in not_a_verdict if c not in NOT_A_VERDICT]
        if unknown:
            raise RuleError(f"{rid}: unknown not_a_signed_verdict condition(s) {unknown}")
        required = [c for c in ("mock", "dry_run", "executor_not_run") if c not in not_a_verdict]
        if required:
            raise RuleError(f"{rid}: not_a_signed_verdict must list {required}: a mock, dry-run or "
                            "'executor: not run' record never certifies")
        sc = rule.get("scorecard") or {}
        kinds = tuple(sc.get("run_kinds") or ())
        blind = sc.get("blind_run_kind")
        if not isinstance(sc.get("schema_id"), str) or not kinds or blind not in kinds:
            raise RuleError(f"{rid}: scorecard block needs schema_id, run_kinds and a blind_run_kind among them")
        if sc.get("headline_run") != HEADLINE_LAST_BLIND:
            raise RuleError(f"{rid}: headline_run {sc.get('headline_run')!r} is not one this code can apply "
                            f"(only {HEADLINE_LAST_BLIND!r})")
        return cls(rule_id=rid, text=text, approved=approved, validity_days=values["validity_days"],
                   max_days_between_blind_runs=values["max_days_between_blind_runs"],
                   never_event_threshold=values["never_event_threshold"], parameter_sources=tuple(sources),
                   statuses=tuple(statuses), not_a_verdict=not_a_verdict, schema_id=sc["schema_id"], run_kinds=kinds,
                   blind_run_kind=blind, builder_labels=tuple(str(x).casefold() for x in sc.get("builder_labels") or ()))

    def parameters(self) -> dict[str, dict[str, Any]]:
        """The three parameters with the id and the approval each one carries in the file."""
        return {name: {"id": pid, "value": getattr(self, name), "approved": approved}
                for name, pid, approved in self.parameter_sources}

    def certified_until(self, verdict_date: date) -> date:
        """Last day of validity: the date of the signed verdict plus ``validity_days``."""
        return verdict_date + timedelta(days=self.validity_days)

    def blind_run_due(self, last_blind_run: date) -> date:
        """Last day on which ``last_blind_run`` is not older than ``max_days_between_blind_runs``."""
        return last_blind_run + timedelta(days=self.max_days_between_blind_runs)


# ---- P4: no new alumnus without a proof pack --------------------------------------------------------------

_ADMISSION_SESSION = "mock or dry-run"


@dataclass(frozen=True)
class AdmissionRule:
    """Rule P4 as written in council.json."""

    rule_id: str
    text: str
    approved: str
    exception_id: str | None
    pack_clause_id: str | None
    min_scenarios: int
    executor_clause_id: str | None

    @classmethod
    def from_council(cls, council: Mapping[str, Any] | None) -> "AdmissionRule | None":
        rule = first_rule(council, "admission")
        return cls._parse(rule) if rule is not None else None

    @classmethod
    def _parse(cls, rule: Mapping[str, Any]) -> "AdmissionRule":
        rid, text, approved = _head(rule, "admission")
        exception_id = None
        for exc in rule.get("exceptions", []) or []:
            if exc.get("when") == {"session": _ADMISSION_SESSION} and exc.get("effect") == "record-only":
                exception_id = exception_id or exc.get("id")
            else:
                raise RuleError(f"{rid}: exception {exc.get('id')!r} is not one this code can apply")
        pack_id = exec_id = None
        min_scenarios = 1
        for clause in rule.get("clauses", []) or []:
            when = clause.get("when") or {}
            if clause.get("effect") != "refuse":
                raise RuleError(f"{rid}: clause {clause.get('id')!r} has no effect this code can apply")
            if set(when) == {"pack_scenarios_below"} and pack_id is None:
                pack_id, min_scenarios = clause.get("id"), int(when["pack_scenarios_below"])
            elif when == {"executor_veto": True} and exec_id is None:
                exec_id = clause.get("id")
            else:
                raise RuleError(f"{rid}: clause {clause.get('id')!r} is not one this code can apply")
        return cls(rule_id=rid, text=text, approved=approved, exception_id=exception_id, pack_clause_id=pack_id,
                   min_scenarios=min_scenarios, executor_clause_id=exec_id)

    def pack_refusal(self, repo_given: bool, scenarios: int) -> str | None:
        """Why the pack clause refuses, or ``None``.  Needs no executor: it can be asked before anything runs."""
        if self.pack_clause_id is None or (repo_given and scenarios >= self.min_scenarios):
            return None
        what = (f"the repository given has {scenarios} scenario(s)" if repo_given else "no --repo given")
        return (f"rule {self.rule_id} ({self.approved}), clause {self.pack_clause_id}: {what}; a defence needs a proof "
                f"pack with at least {self.min_scenarios} scenario(s) (\"{self.text}\")")

    def evaluate(self, *, repo_given: bool, scenarios: int, executor: ExecutorRuling | None, live: bool) -> dict[str, Any]:
        """Apply the rule.  ``live`` sessions are refused; mock / dry-run sessions are only recorded (the
        exception), unless the file has no such exception, in which case they are refused too."""
        reasons: list[str] = []
        fired: list[str] = []
        pack_why = self.pack_refusal(repo_given, scenarios)
        if pack_why:
            fired.append(self.pack_clause_id)
            reasons.append(pack_why)
        executor_state = executor.executor if executor is not None else None
        if self.executor_clause_id and executor is not None and executor.veto:
            fired.append(self.executor_clause_id)
            reasons.append(f"rule {self.rule_id} ({self.approved}), clause {self.executor_clause_id}: the pack does not pass "
                           f"the executor: {executor.veto_short}")
        admitted = not fired
        enforced = live or self.exception_id is None
        notes = []
        if self.executor_clause_id and executor_state != RAN:
            notes.append(f"{self.executor_clause_id} not checked: executor {executor_state or 'result absent'}")
        if not admitted and not enforced:
            notes.append(f"{self.exception_id}: mock / dry-run session: the admission rule would have refused "
                         "a live defence; this session ran anyway")
        return {"rule_id": self.rule_id, "approved": self.approved, "text": self.text,
                "pack": {"repo_given": bool(repo_given), "scenarios": int(scenarios), "min_scenarios": self.min_scenarios},
                "executor": executor_state, "clauses_fired": fired, "admitted": admitted, "enforced": enforced,
                "refused": bool(not admitted and enforced), "would_refuse": bool(not admitted and not enforced),
                "exception": (self.exception_id if (not admitted and not enforced) else None),
                "reasons": reasons, "notes": notes}
