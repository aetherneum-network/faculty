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
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

NOT_RUN = "not run"
RAN = "ran"
NOTHING_TO_EXECUTE = "no scenarios/ directory: nothing to execute"

# executor status -> the counter that holds it in ExecutorResult / the summary
STATUS_COUNTER = {"pass": "passed", "fail": "failed", "error": "errors", "timeout": "timeouts"}
COUNT_KEYS = ("scenarios_found", "passed", "failed", "errors", "timeouts")
_WHEN_KEYS = {"executor", "scenarios_found_min", "passed_below_found", "scenarios_started_max"}
_MAX_LISTED = 12


class RuleError(ValueError):
    """The rules block of council.json cannot be read as written."""


def executor_summary(run_executor: bool, result: Mapping[str, Any] | None, error: str | None = None) -> dict[str, Any]:
    """What the executor did, in the shape the rule reads (and the records sign).

    ``result`` is ``ExecutorResult.to_dict()`` or ``None`` (nothing was executed).
    """
    if not run_executor:
        return {"executor": NOT_RUN, "counts": None, "not_passed": [], "error": None}
    if result is None:
        return {"executor": RAN, "counts": {k: 0 for k in COUNT_KEYS}, "not_passed": [],
                "error": error or NOTHING_TO_EXECUTE}
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
        veto_id = zero_id = None
        found_min, outcome, started_max, art_count = 1, "VETO", 0, 0
        started: tuple[str, ...] = ("pass", "fail", "timeout")
        for clause in rule.get("clauses", []) or []:
            when, effect = clause.get("when") or {}, clause.get("effect") or {}
            cls._check_when(rid, when)
            if "outcome" in effect and veto_id is None:
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
                   started_statuses=started, live_requires_executor=bool(rule.get("live_requires_executor", False)))

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
        ruling = ExecutorRuling(**base, executor=RAN, counts=c, fired=False, not_passed=not_passed)
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
        ruling.fired = bool(ruling.clauses_fired)
        if not ruling.fired:
            ruling.reasons.append(f"{self.rule_id} silent: {passed} of {found} declared scenario(s) passed")
        return ruling


def ruling_for(council: Mapping[str, Any] | None, summary: Mapping[str, Any] | None) -> ExecutorRuling | None:
    """Apply the executor rule of ``council`` to ``summary``; ``None`` when there is no rule or no summary."""
    if summary is None:
        return None
    rule = ExecutorRule.from_council(council)
    return rule.evaluate(summary) if rule else None
