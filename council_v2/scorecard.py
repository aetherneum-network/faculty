"""Scorecard of a proof pack and status of a diploma (rule P3, Rector, 2026-09-30).

"The diploma is a blind number that expires."

Two things live here; both only *apply* what ``council/council.json`` says
(``rules.DiplomaRule`` extracts it, operating rule R7):

1. The scorecard validator.  ``scorecard.schema.json`` (next to this file)
   fixes the shape; ``check`` adds what a schema cannot say: runs in date
   order, ``headline_run`` = the LAST out-of-pool run (never the best), no run
   run by the builder, no seed used twice, and every run of the previous
   signed version still there, unaltered.  A scorecard that fails is refused
   (``ScorecardRefused``), never repaired.

2. ``derive_status``: one pure function from (pack or none, signed verdict or
   none, scorecard or none, the date given, the rule with its three
   parameters, executor veto of rule EX-1) to one of ``profile-attested``,
   ``evidence-pending``, ``certified``, ``lapsed``, ``under-review``.  The date
   is an argument: nothing in this module reads a clock.

Reading of the two day limits (both inclusive): the diploma is inside its
validity while ``today <= verdict date + validity_days``; a blind run is not
too old while ``today - run date <= max_days_between_blind_runs``.  Dates are
UTC calendar dates.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from . import rules

SCHEMA_PATH = Path(__file__).with_name("scorecard.schema.json")
FILE_SUFFIX = ".scorecard.json"
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
OUTCOME_PASS = "PASS"

PROFILE_ATTESTED, EVIDENCE_PENDING, CERTIFIED, LAPSED, UNDER_REVIEW = (
    "profile-attested", "evidence-pending", "certified", "lapsed", "under-review")


def parse_utc(text: str) -> datetime:
    """``2026-09-30T15:34:00Z`` -> aware UTC datetime (``ValueError`` otherwise)."""
    return datetime.strptime(text, UTC_FORMAT).replace(tzinfo=timezone.utc)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# ======================================================================================================
# Shape: a small reader of the JSON Schema file (only the keywords that file uses)
# ======================================================================================================

_ANNOTATIONS = {"$schema", "$id", "title", "description"}
_KEYWORDS = {"type", "required", "properties", "items", "enum", "const", "minimum", "minItems", "minLength", "pattern"}
_TYPES: dict[str, Any] = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float),
                          "boolean": bool, "null": type(None)}


def _unsupported(schema: Any, path: str = "") -> list[str]:
    if not isinstance(schema, Mapping):
        return []
    out = [f"{path}/{k}" for k in schema if k not in _ANNOTATIONS and k not in _KEYWORDS]
    for key, sub in (schema.get("properties") or {}).items():
        out += _unsupported(sub, f"{path}/properties/{key}")
    out += _unsupported(schema.get("items"), f"{path}/items")
    return out


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    schema = json.loads(Path(path).read_text(encoding="utf-8"))
    unknown = _unsupported(schema)
    if unknown:  # a keyword this reader would silently ignore is an error, never ignored
        raise rules.RuleError(f"{Path(path).name}: keyword(s) this validator does not apply: {unknown}")
    return schema


def _is_type(value: Any, name: str) -> bool:
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[name])


def schema_errors(value: Any, schema: Mapping[str, Any], path: str = "") -> list[tuple[str, str, str]]:
    """``[(keyword, path, message)]`` for ``value`` against ``schema`` (the subset in ``_KEYWORDS``)."""
    out: list[tuple[str, str, str]] = []
    where = path or "(top level)"
    if "const" in schema and value != schema["const"]:
        out.append(("const", path, f"{where} must be {schema['const']!r}, not {value!r}"))
    if "enum" in schema and value not in schema["enum"]:
        out.append(("enum", path, f"{where} must be one of {list(schema['enum'])}, not {value!r}"))
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, n) for n in names):
            out.append(("type", path, f"{where} must be of type {' or '.join(names)}, not {type(value).__name__}"))
            return out
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            out.append(("minLength", path, f"{where} must not be empty"))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(("pattern", path, f"{where} {value!r} does not have the required form"))
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema and value < schema["minimum"]:
        out.append(("minimum", path, f"{where} must be >= {schema['minimum']}, not {value}"))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                out.append(("required", f"{path}/{key}", f"{where}: required field {key!r} is missing"))
        for key, sub in (schema.get("properties") or {}).items():
            if key in value:
                out += schema_errors(value[key], sub, f"{path}/{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            out.append(("minItems", path, f"{where} must list at least {schema['minItems']} item(s)"))
        if "items" in schema:
            for i, item in enumerate(value):
                out += schema_errors(item, schema["items"], f"{path}/{i}")
    return out


# ======================================================================================================
# Refusals
# ======================================================================================================

@dataclass(frozen=True)
class Refusal:
    code: str  # schema | required-field | run-kind | run-date | run-order | headline-run | run-by-builder |
    #            written-by-builder | seed-reused | runs-removed | unreadable
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ScorecardRefused(ValueError):
    """The scorecard does not satisfy rule P3.  ``refusals`` lists every reason found."""

    def __init__(self, refusals: list[Refusal], rule_id: str = "P3", source: str | None = None):
        self.refusals = list(refusals)
        self.codes = [r.code for r in self.refusals]
        self.rule_id = rule_id
        what = f"scorecard {source}" if source else "scorecard"
        super().__init__(f"{what} refused (rule {rule_id}): " + "; ".join(str(r) for r in self.refusals))


_ARTICLES = {"the", "a", "an"}


def is_builder(who: str, builder_labels: tuple[str, ...], builder_name: str | None = None) -> bool:
    """True when ``who`` names the builder: its first word (articles aside) is a builder label, or it is
    the ``builder`` the scorecard itself names.  "evaluator, not the builder" is not the builder."""
    words = [w for w in re.findall(r"[a-z0-9]+", who.casefold()) if w not in _ARTICLES]
    if words and words[0] in builder_labels:
        return True
    return bool(builder_name) and who.strip().casefold() == str(builder_name).strip().casefold()


def run_digest(run: Mapping[str, Any]) -> str:
    """sha256 of one run as written (canonical JSON): what 'kept, unaltered' is checked against."""
    return sha256_bytes(json.dumps(run, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _previous_runs(previous: Mapping[str, Any]) -> tuple[int, list[dict[str, Any]] | None]:
    """(number of runs, [{run_at_utc, seed, kind, sha256}] or None) of a previous signed version.

    ``previous`` is either the summary signed in a decision record (``Scorecard.summary()``) or a whole
    previous scorecard document.
    """
    if isinstance(previous.get("run_digests"), list):
        return int(previous.get("runs", len(previous["run_digests"]))), [dict(x) for x in previous["run_digests"]]
    runs = previous.get("runs")
    if isinstance(runs, list):
        return len(runs), [{"run_at_utc": r.get("run_at_utc"), "seed": r.get("seed"), "kind": r.get("kind"),
                            "sha256": run_digest(r)} for r in runs]
    if isinstance(runs, int) and not isinstance(runs, bool):
        return runs, None
    raise ValueError("previous signed version: neither 'run_digests' nor 'runs' can be read")


def _refusal_code(keyword: str, path: str) -> str:
    if keyword == "required":
        return "required-field"
    if keyword == "enum" and re.fullmatch(r"/runs/\d+/kind", path):
        return "run-kind"
    return "schema"


def check(data: Any, rule: rules.DiplomaRule, *, previous: Mapping[str, Any] | None = None) -> list[Refusal]:
    """Every reason to refuse ``data`` as a scorecard; an empty list means it is accepted."""
    if not isinstance(data, Mapping):
        return [Refusal("schema", "the scorecard is not a JSON object")]
    schema = load_schema()
    declared_id = (schema.get("properties") or {}).get("schema", {}).get("const")
    declared_kinds = ((schema.get("properties") or {}).get("runs", {}).get("items", {}).get("properties", {})
                      .get("kind", {}).get("enum") or [])
    if declared_id != rule.schema_id or sorted(declared_kinds) != sorted(rule.run_kinds):
        raise rules.RuleError(f"{rule.rule_id}: council.json names schema {rule.schema_id!r} with run kinds "
                              f"{list(rule.run_kinds)}, {SCHEMA_PATH.name} says {declared_id!r} with {declared_kinds}")
    refusals = [Refusal(_refusal_code(kw, path), msg) for kw, path, msg in schema_errors(data, schema)]
    if refusals:
        return refusals  # the checks below need a well-formed document
    runs = data["runs"]
    times: list[datetime] = []
    for i, r in enumerate(runs):
        try:
            times.append(parse_utc(r["run_at_utc"]))
        except ValueError:
            refusals.append(Refusal("run-date", f"runs[{i}].run_at_utc {r['run_at_utc']!r} is not a UTC date-time"))
    if refusals:
        return refusals
    for i in range(1, len(runs)):
        if times[i] < times[i - 1]:
            refusals.append(Refusal("run-order", f"runs[{i}] ({runs[i]['run_at_utc']}) is earlier than runs[{i - 1}] "
                                                 f"({runs[i - 1]['run_at_utc']}): runs are listed in date order"))
    builder = data.get("builder")
    for i, r in enumerate(runs):
        if is_builder(r["run_by"], rule.builder_labels, builder):
            refusals.append(Refusal("run-by-builder", f"runs[{i}].run_by is {r['run_by']!r}: a run counts only if run by "
                                                      "a hand other than the builder"))
    if is_builder(data["written_by"], rule.builder_labels, builder):
        refusals.append(Refusal("written-by-builder", f"written_by is {data['written_by']!r}: the scorecard is written "
                                                      "by the evaluator, never by the builder"))
    seen: dict[str, int] = {}
    for i, r in enumerate(runs):
        key = str(r["seed"])
        if key in seen:
            refusals.append(Refusal("seed-reused", f"runs[{i}].seed {r['seed']!r} was already used by runs[{seen[key]}]: "
                                                   "a run counts only with a seed never used before"))
        else:
            seen[key] = i
    blind = [i for i, r in enumerate(runs) if r["kind"] == rule.blind_run_kind]
    expected = blind[-1] if blind else None
    if data["headline_run"] != expected:
        refusals.append(Refusal("headline-run", f"headline_run is {data['headline_run']!r}; it must be {expected!r}: the "
                                                f"LAST {rule.blind_run_kind} run, never the best"))
    if previous is not None:
        prev_n, prev_runs = _previous_runs(previous)
        if len(runs) < prev_n:
            refusals.append(Refusal("runs-removed", f"{len(runs)} run(s) listed, the previous signed version had {prev_n}: "
                                                    "every run is kept, the unfavourable ones too"))
        if prev_runs is not None:
            now_digests = {run_digest(r) for r in runs}
            gone = [p for p in prev_runs if p.get("sha256") not in now_digests]
            if gone:
                listed = ", ".join(f"{p.get('run_at_utc')} seed {p.get('seed')} ({p.get('kind')})" for p in gone)
                refusals.append(Refusal("runs-removed", f"{len(gone)} run(s) of the previous signed version are missing "
                                                        f"or altered: {listed}"))
    return refusals


# ======================================================================================================
# An accepted scorecard
# ======================================================================================================

@dataclass(frozen=True)
class Run:
    index: int
    run_at: datetime
    seed: Any
    kind: str
    run_by: str
    n: int
    abstained: int
    never_events: int
    sha256: str


@dataclass(frozen=True)
class Scorecard:
    """A scorecard that passed ``check``.  Build it with ``validate`` or ``load``, never by hand."""

    data: Mapping[str, Any]
    runs: tuple[Run, ...]
    headline: Run | None  # the last blind (out-of-pool) run
    sha256: str | None = None  # of the file bytes, when it came from a file
    source: str | None = None  # file name only

    @property
    def alumnus(self) -> str:
        return self.data["alumnus"]

    @property
    def last_blind_run(self) -> Run | None:
        return self.headline

    def summary(self) -> dict[str, Any]:
        """What a decision record signs about the scorecard it relied on."""
        d = self.data
        return {"file": self.source, "sha256": self.sha256, "schema": d["schema"], "alumnus": d["alumnus"],
                "pack_version": d["pack_version"], "freeze_tag": d["freeze_tag"], "freeze_commit": d["freeze_commit"],
                "runs": len(self.runs), "headline_run": self.headline.index if self.headline else None,
                "run_digests": [{"run_at_utc": d["runs"][r.index]["run_at_utc"], "seed": r.seed, "kind": r.kind,
                                 "sha256": r.sha256} for r in self.runs]}


def validate(data: Any, rule: rules.DiplomaRule, *, previous: Mapping[str, Any] | None = None,
             sha256: str | None = None, source: str | None = None) -> Scorecard:
    """Return the accepted ``Scorecard`` or raise ``ScorecardRefused`` with every reason."""
    refusals = check(data, rule, previous=previous)
    if refusals:
        raise ScorecardRefused(refusals, rule.rule_id, source)
    runs = tuple(Run(index=i, run_at=parse_utc(r["run_at_utc"]), seed=r["seed"], kind=r["kind"], run_by=r["run_by"],
                     n=r["n"], abstained=r["abstained"], never_events=r["never_events"], sha256=run_digest(r))
                 for i, r in enumerate(data["runs"]))
    blind = [r for r in runs if r.kind == rule.blind_run_kind]
    return Scorecard(data=data, runs=runs, headline=blind[-1] if blind else None, sha256=sha256, source=source)


@dataclass(frozen=True)
class RawScorecard:
    """A scorecard file as read: parsed JSON and the sha256 of its bytes.  Not validated yet."""

    data: Any
    sha256: str
    source: str


def read_raw(path: str | Path) -> RawScorecard:
    p = Path(path)
    try:
        raw = p.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ScorecardRefused([Refusal("unreadable", f"{type(e).__name__}: {e}")], source=p.name) from e
    return RawScorecard(data=data, sha256=sha256_bytes(raw), source=p.name)


def load(path: str | Path, rule: rules.DiplomaRule, *, previous: Mapping[str, Any] | None = None) -> Scorecard:
    """Read and validate a scorecard file; its ``sha256`` is the digest of the bytes read."""
    raw = read_raw(path)
    return validate(raw.data, rule, previous=previous, sha256=raw.sha256, source=raw.source)


def load_dir(directory: str | Path) -> tuple[dict[str, RawScorecard], list[str]]:
    """Every ``*.scorecard.json`` of a directory, by alumnus slug, not validated.  Returns (scorecards, notes)."""
    found: dict[str, RawScorecard] = {}
    notes: list[str] = []
    for p in sorted(Path(directory).glob("*" + FILE_SUFFIX)):
        try:
            raw = read_raw(p)
        except ScorecardRefused as e:
            notes.append(str(e))
            continue
        slug = raw.data.get("alumnus") if isinstance(raw.data, Mapping) else None
        slug = slug if isinstance(slug, str) and slug else p.name[: -len(FILE_SUFFIX)]
        if slug in found:
            notes.append(f"{p.name}: a second scorecard for {slug!r}; {found[slug].source} is used")
            continue
        found[slug] = raw
    return found, notes


# ======================================================================================================
# Status of a diploma
# ======================================================================================================

@dataclass(frozen=True)
class Verdict:
    """What rule P3 reads of a signed decision record."""

    outcome: str | None
    signed_at: datetime  # UTC, ``recorded_at`` of the signed decision record
    executor: str | None  # "ran" | "not run" | None (the record carries no executor ruling)
    mock: bool = False
    dry_run: bool = False
    scorecard_sha256: str | None = None

    @classmethod
    def from_decision_record(cls, rec: Mapping[str, Any], *, outcome: str | None = None, executor: str | None = None,
                             mock: bool | None = None) -> "Verdict":
        """``outcome`` / ``executor`` / ``mock`` override what the record stores when the caller has
        recomputed them from the signed seat records (the Registry does)."""
        session = rec.get("session") or {}
        return cls(outcome=outcome if outcome is not None else (rec.get("decision") or {}).get("outcome"),
                   signed_at=parse_utc(rec["recorded_at"]),
                   executor=executor if executor is not None else (rec.get("executor_rule") or {}).get("executor"),
                   mock=bool(session.get("mock")) if mock is None else bool(mock),
                   dry_run=bool(rec.get("dry_run") or session.get("dry_run")),
                   scorecard_sha256=(rec.get("scorecard") or {}).get("sha256"))


def not_a_verdict_reasons(verdict: Verdict | None, rule: rules.DiplomaRule) -> list[str]:
    """Why ``verdict`` is not a signed verdict for rule P3 (empty list: it is one)."""
    if verdict is None:
        return ["no signed verdict"]
    holds = {
        "mock": (verdict.mock, "the session is mock: not a Council verdict"),
        "dry_run": (verdict.dry_run, "the session is a dry run: not a Council verdict"),
        "executor_not_run": (verdict.executor != rules.RAN,
                             f"the record says 'executor: {verdict.executor or 'no result'}': it never certifies"),
        "outcome_not_pass": (verdict.outcome != OUTCOME_PASS, f"the signed outcome is {verdict.outcome}, not {OUTCOME_PASS}"),
        "no_scorecard_digest": (not verdict.scorecard_sha256, "the signed record relied on no scorecard"),
    }
    return [holds[c][1] for c in rule.not_a_verdict if holds[c][0]]


@dataclass(frozen=True)
class Status:
    status: str
    clause_id: str  # the entry of the rule's ordered list that decided
    rule_id: str
    approved: str
    as_of: date
    conditions: tuple[str, ...]  # the conditions of that entry that hold
    reasons: tuple[str, ...]
    certified_until: date | None  # verdict date + validity_days; None without a signed verdict
    last_blind_run: date | None
    blind_run_due: date | None  # last blind run + max_days_between_blind_runs
    headline_run: int | None
    facts: Mapping[str, bool]
    parameters: Mapping[str, Any]
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {"status": self.status, "clause_id": self.clause_id, "rule_id": self.rule_id, "approved": self.approved,
                "as_of": iso(self.as_of), "conditions": list(self.conditions), "reasons": list(self.reasons),
                "certified_until": iso(self.certified_until), "last_blind_run": iso(self.last_blind_run),
                "blind_run_due": iso(self.blind_run_due), "headline_run": self.headline_run, "facts": dict(self.facts),
                "parameters": dict(self.parameters), "notes": list(self.notes)}


def derive_status(*, pack: bool, verdict: Verdict | None, scorecard: Scorecard | None, today: date,
                  rule: rules.DiplomaRule, executor_veto: bool) -> Status:
    """The status of a diploma.  Pure: same arguments, same answer; ``today`` is given, never read.

    ``pack``           a proof pack exists (at least one scenario, or a measured frozen pack)
    ``verdict``        the signed decision record, or ``None``
    ``scorecard``      the current accepted scorecard, or ``None``
    ``today``          the date the status is asked for (a ``date``, UTC)
    ``rule``           rule P3 as extracted from council.json (the three parameters and the ordered statuses)
    ``executor_veto``  rule EX-1 vetoes the pack
    """
    if type(today) is not date:  # a datetime would let the time of day leak into a day count
        raise TypeError("today must be a datetime.date")
    threshold = rule.never_event_threshold
    why_not = not_a_verdict_reasons(verdict, rule)
    signed = not why_not
    headline = scorecard.headline if scorecard else None
    certified_until = rule.certified_until(verdict.signed_at.date()) if signed else None
    last_blind = headline.run_at.date() if headline else None
    blind_age = (today - last_blind).days if last_blind else None
    after = [r for r in scorecard.runs if r.run_at > verdict.signed_at and r.never_events >= threshold] \
        if (signed and scorecard) else []
    facts = {
        "no_pack": not pack,
        "executor_veto": bool(executor_veto),
        "never_event_in_headline_run": bool(headline and headline.never_events >= threshold),
        "never_event_after_verdict": bool(after),
        "no_signed_verdict": not signed,
        "validity_over": bool(signed and today > certified_until),
        "blind_run_too_old": bool(signed and (blind_age is None or blind_age > rule.max_days_between_blind_runs)),
        "otherwise": True,
    }
    for clause_id, status, conditions in rule.statuses:  # first entry with a condition that holds wins
        held = tuple(c for c in conditions if facts[c])
        if held:
            break
    else:
        raise rules.RuleError(f"{rule.rule_id}: no status applies; the ordered list needs a final 'otherwise' entry")

    text = {
        "no_pack": "no proof pack",
        "executor_veto": "executor veto (rule EX-1)",
        "never_event_in_headline_run": (f"the headline run (runs[{headline.index}], {headline.run_at.date()}) has "
                                        f"{headline.never_events} never-event(s); threshold {threshold}") if headline else "",
        "never_event_after_verdict": "never-event(s) in run(s) after the signed verdict: "
                                     + ", ".join(f"runs[{r.index}] ({r.run_at.date()}, {r.never_events})" for r in after),
        "no_signed_verdict": "; ".join(why_not),
        "validity_over": f"validity over: certified until {certified_until}, status asked for {today}",
        "blind_run_too_old": (f"last valid blind run {last_blind} is {blind_age} days old; maximum "
                              f"{rule.max_days_between_blind_runs}") if last_blind else "no valid blind run on the scorecard",
        "otherwise": (f"signed verdict of {verdict.signed_at.date()}, certified until {certified_until}; last valid blind "
                      f"run {last_blind} ({blind_age} days old, next due by "
                      f"{rule.blind_run_due(last_blind)}); no never-event in the headline run") if signed and last_blind else "",
    }
    notes = []
    if pack and scorecard is None:
        notes.append("no accepted scorecard: the pack is not measured")
    declared = scorecard.data.get("status") if scorecard else None
    if declared and declared != status:
        notes.append(f"the scorecard file says status {declared!r}; that field is informative, the derived status is {status!r}")
    if signed and scorecard and scorecard.sha256 and verdict.scorecard_sha256 != scorecard.sha256:
        notes.append("the scorecard has changed since the verdict (digest differs): runs were added after it")
    return Status(status=status, clause_id=clause_id, rule_id=rule.rule_id, approved=rule.approved, as_of=today,
                  conditions=held, reasons=tuple(text[c] for c in held), certified_until=certified_until,
                  last_blind_run=last_blind, blind_run_due=rule.blind_run_due(last_blind) if last_blind else None,
                  headline_run=headline.index if headline else None, facts=facts, parameters=rule.parameters(),
                  notes=tuple(notes))
