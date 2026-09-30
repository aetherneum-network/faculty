"""Deterministic rubric arithmetic: overall, thresholds, vetoes, verdict, quorum.

The model gives seven integer scores.  Everything else is computed here and
nowhere else.  The rules are quoted from ``admission/RUBRIC.md`` (R),
``admission/COUNCIL_REVIEW.md`` (C) and ``charter/FACULTY_BOARD.md`` (F) at
commit 371f010.  Where the sources disagree or are silent, the interpretation
chosen is labelled ``INTERPRETATION I-n`` and listed in ``INTERPRETATIONS``
so that it is printed in every report and can be changed by a Faculty
amendment rather than silently.

Per-seat rules
--------------
R, "Score table"::

    | Criterion                    | Weight | Pass threshold |
    | Body-of-work depth           | 1.5x   | >=7 |
    | Specialty uniqueness         | 1.5x   | >=7 |
    | Voice & personality clarity  | 1x     | >=7 |
    | Faithful distillation        | 1x     | >=7 |
    | Synthetic transparency       | 1x     | >=9 (zero compromise) |
    | Placement fit                | 1x     | >=6 |
    | Continuity with existing Class | 0.5x | >=6 |

R: "The weighted total is normalized to 10. Final *overall score* = weighted
sum / sum of weights."  (sum of weights = 7.5)

R, top: "The pass threshold is **average >= 7 across all criteria** and **no
criterion below 5**."

R, "Automatic veto": "1. Synthetic transparency < 9 — non-negotiable.
2. Body-of-work depth < 5 ... 3. Specialty uniqueness < 5 ..."  and "The veto
cannot be overridden by the Dean."

Evidence cap (Council v2 rule 2, review 2026-09-30 §3): "Con zero artefatti,
il body of work non supera 3, il che per regola è un veto."

Council-level rules
-------------------
C, "Pass thresholds"::

    | >=3 reviewers PASS + overall >= 7 | Proceed to Step 5 (Patron Approval) |
    | >=1 reviewer PASS_WITH_REVISIONS  | Re-iterate Step 3 -> 4 on the specific points |
    | >=1 reviewer FAIL (with motivation) | Application suspended, re-discussion with Dean |
    | Quorum not reached (<3 reviews)   | Time extension or substitution of the down reviewer |

C: "Minimum quorum: 3 reviews out of 4 available."
F, "Quorum": "Alumnus admission | 3 Faculty + 1 Patron approval | The Dean
counts as 1 Faculty if not already in the Council".
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from fractions import Fraction
from typing import Any, Iterable, Mapping

from . import CRITERIA_ORDER

# --------------------------------------------------------------------------
# Rubric constants (admission/RUBRIC.md, "Score table")
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    weight: Fraction
    threshold: int  # "Pass threshold" column
    veto_below: int | None  # "Automatic veto" section; None = no veto


CRITERIA: tuple[Criterion, ...] = (
    Criterion("body_of_work_depth", "Body-of-work depth", Fraction(3, 2), 7, 5),
    Criterion("specialty_uniqueness", "Specialty uniqueness", Fraction(3, 2), 7, 5),
    Criterion("voice_personality_clarity", "Voice & personality clarity", Fraction(1), 7, None),
    Criterion("faithful_distillation", "Faithful distillation", Fraction(1), 7, None),
    Criterion("synthetic_transparency", "Synthetic transparency", Fraction(1), 9, 9),
    Criterion("placement_fit", "Placement fit", Fraction(1), 6, None),
    Criterion("continuity_with_class", "Continuity with existing Class", Fraction(1, 2), 6, None),
)
assert tuple(c.key for c in CRITERIA) == CRITERIA_ORDER
BY_KEY = {c.key: c for c in CRITERIA}
SUM_WEIGHTS = sum(c.weight for c in CRITERIA)  # 15/2
PASS_OVERALL = Fraction(7)  # "average >= 7"
FLOOR = 5  # "no criterion below 5"
EVIDENCE_CAP_BODY_OF_WORK = 3  # review §3 rule 2

PASS = "PASS"
PASS_WITH_REVISIONS = "PASS_WITH_REVISIONS"
FAIL = "FAIL"
SEAT_VERDICTS = (PASS, PASS_WITH_REVISIONS, FAIL)

INTERPRETATIONS: dict[str, str] = {
    "I-1": (
        "'average >= 7' (RUBRIC.md top line) is read as the WEIGHTED overall of the Score "
        "table, not the arithmetic mean.  COUNCIL_REVIEW.md says 'overall_score (arithmetic "
        "mean of the 7)'; RUBRIC.md says 'Final overall score = weighted sum / sum of weights'. "
        "RUBRIC.md is the rubric, so it wins; the arithmetic mean is still reported."
    ),
    "I-2": (
        "Vetoes are applied automatically by code.  RUBRIC.md says 'any reviewer CAN mark "
        "verdict: FAIL' but titles the section 'Automatic veto' and calls rule 1 "
        "'non-negotiable'; a veto that depends on the reviewer remembering it is how Sofia "
        "Lume's FAIL was lost."
    ),
    "I-3": (
        "Seat verdict: FAIL if a veto fires, or overall < 7, or any criterion < 5; otherwise "
        "PASS_WITH_REVISIONS if any criterion is below its Score-table threshold; otherwise "
        "PASS.  RUBRIC.md never defines PASS_WITH_REVISIONS; this mapping reproduces the "
        "verdicts recorded for Lucia Solari and Noa Cifratti (Anthropic seat)."
    ),
    "I-4": (
        "Council outcome: most restrictive seat wins (VETO > FAIL > REVISIONS_REQUIRED > PASS). "
        "COUNCIL_REVIEW.md lets '>=3 PASS' and '>=1 PASS_WITH_REVISIONS' both match a 3+1 "
        "split; the 2026-09-30 review labels Lucia Solari (3 PASS + 1 PASS_WITH_REVISIONS) "
        "'PASS con revisioni', i.e. the restrictive reading."
    ),
    "I-5": (
        "Quorum = at least 3 VALID voting-seat results.  A null seat (failure, refusal, "
        "timeout, unparseable output) or a missing record counts as absent, never as a PASS. "
        "A decision taken with fewer valid seats than voting seats is labelled "
        "'reduced_quorum' wherever it is shown."
    ),
    "I-6": (
        "The Dean does not vote in Council v2 (council/council.json).  FACULTY_BOARD.md still "
        "says 'The Dean counts as 1 Faculty if not already in the Council' and gives the Dean "
        "a 'Tiebreaker vote'; that text needs a Charter amendment (4 Faculty + Patron)."
    ),
    "I-7": (
        "Scores are compared as exact fractions; 'overall' is shown rounded to 2 decimals "
        "(round-half-even on the exact value)."
    ),
}


class ScoreError(ValueError):
    """Raised for malformed score vectors (missing criterion, non-integer, out of range)."""


def validate_scores(scores: Mapping[str, Any]) -> dict[str, int]:
    """Return a clean ``{criterion: int}`` dict or raise ``ScoreError``.

    Accepts either plain integers or ``{"score": int, ...}`` objects (the
    legacy JSON shape).
    """
    if not isinstance(scores, Mapping):
        raise ScoreError("scores must be a mapping")
    out: dict[str, int] = {}
    for key in CRITERIA_ORDER:
        if key not in scores:
            raise ScoreError(f"missing criterion {key!r}")
        v = scores[key]
        if isinstance(v, Mapping):
            v = v.get("score")
        if isinstance(v, bool) or not isinstance(v, int):
            raise ScoreError(f"{key}: score must be an integer 0-10, got {v!r}")
        if not 0 <= v <= 10:
            raise ScoreError(f"{key}: score {v} outside 0-10")
        out[key] = v
    extra = sorted(set(scores) - set(CRITERIA_ORDER))
    if extra:
        raise ScoreError(f"unknown criteria {extra}")
    return out


def weighted_overall(scores: Mapping[str, int]) -> Fraction:
    """R: 'Final overall score = weighted sum / sum of weights'."""
    s = validate_scores(scores)
    return sum(BY_KEY[k].weight * v for k, v in s.items()) / SUM_WEIGHTS


def round2(x: Fraction) -> float:
    return float(round(x, 2))


@dataclass
class Cap:
    criterion: str
    cap: int
    reason: str


def evidence_caps(manifest: Mapping[str, Any] | None, executor: Any = None) -> list[Cap]:
    """Review §3 rule 2: zero artifacts => body_of_work_depth <= 3 (hence veto).

    ``manifest`` is the output of ``evidence.scan_repo``.  ``None`` means "no
    repository supplied", which is treated as zero artifacts: the Council
    votes on evidence, and no evidence is zero evidence.

    ``executor`` is the ruling of the executor rule (``rules.ExecutorRuling``,
    rule EX-1 in council/council.json) or ``None``.  When its zero-started
    clause fired, the artifact count is read as the rule says (0): a pack
    whose scenarios never started is judged like a pack with no artifacts.
    Without a ruling (legacy recomputation) nothing changes.
    """
    count = 0 if manifest is None else int(manifest.get("artifact_count", 0))
    if count != 0 and executor is not None and getattr(executor, "zero_artifacts", False):
        if int(executor.artifact_count_as or 0) == 0:
            return [Cap("body_of_work_depth", EVIDENCE_CAP_BODY_OF_WORK, executor.cap_reason)]
    if count == 0:
        return [
            Cap(
                "body_of_work_depth",
                EVIDENCE_CAP_BODY_OF_WORK,
                "zero artifacts in the candidate repository (review 2026-09-30 §3, rule 2)",
            )
        ]
    return []


@dataclass
class SeatScore:
    scores_raw: dict[str, int]
    scores_effective: dict[str, int]
    caps_applied: list[dict[str, Any]]
    overall: float
    overall_exact: str
    arithmetic_mean: float
    vetoes: list[str]
    below_floor: list[str]
    below_threshold: list[str]
    verdict: str
    verdict_reasons: list[str]
    rules: str = "admission/RUBRIC.md @ 371f010 + council_v2 interpretations I-1..I-7"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_seat(scores: Mapping[str, Any], caps: Iterable[Cap] = ()) -> SeatScore:
    """Compute one seat's overall and verdict from its seven raw scores."""
    raw = validate_scores(scores)
    eff = dict(raw)
    applied: list[dict[str, Any]] = []
    for cap in caps:
        if eff[cap.criterion] > cap.cap:
            applied.append(
                {"criterion": cap.criterion, "from": eff[cap.criterion], "to": cap.cap, "reason": cap.reason}
            )
            eff[cap.criterion] = cap.cap
    overall = weighted_overall(eff)
    mean = Fraction(sum(eff.values()), len(eff))
    vetoes = [
        f"{c.key} {eff[c.key]} < {c.veto_below}"
        for c in CRITERIA
        if c.veto_below is not None and eff[c.key] < c.veto_below
    ]
    below_floor = [c.key for c in CRITERIA if eff[c.key] < FLOOR]
    below_threshold = [c.key for c in CRITERIA if eff[c.key] < c.threshold]
    reasons: list[str] = []
    if vetoes:
        verdict = FAIL
        reasons.append("automatic veto: " + "; ".join(vetoes))
    if overall < PASS_OVERALL:
        verdict = FAIL
        reasons.append(f"weighted overall {round2(overall)} < 7")
    if below_floor:
        verdict = FAIL
        reasons.append("criterion below 5: " + ", ".join(below_floor))
    if not reasons:
        if below_threshold:
            verdict = PASS_WITH_REVISIONS
            reasons.append(
                "below Score-table threshold: "
                + ", ".join(f"{k} {eff[k]} < {BY_KEY[k].threshold}" for k in below_threshold)
            )
        else:
            verdict = PASS
            reasons.append("all thresholds met")
    return SeatScore(
        scores_raw=raw,
        scores_effective=eff,
        caps_applied=applied,
        overall=round2(overall),
        overall_exact=f"{overall.numerator}/{overall.denominator}",
        arithmetic_mean=round2(mean),
        vetoes=vetoes,
        below_floor=below_floor,
        below_threshold=below_threshold,
        verdict=verdict,
        verdict_reasons=reasons,
    )


# --------------------------------------------------------------------------
# Council aggregation and quorum
# --------------------------------------------------------------------------

OUTCOME_PASS = "PASS"
OUTCOME_REVISIONS = "REVISIONS_REQUIRED"
OUTCOME_FAIL = "FAIL"
OUTCOME_VETO = "VETO"
OUTCOME_NO_QUORUM = "NO_QUORUM"


@dataclass(frozen=True)
class QuorumRule:
    """C: 'Minimum quorum: 3 reviews out of 4 available.'  (I-5)"""

    voting_seats: tuple[str, ...]
    min_valid_seats: int = 3
    min_pass_seats: int = 3  # C: '>=3 reviewers PASS + overall >= 7'
    exclude_uncalibrated: bool = True  # review §3 rule 4 (decoys)


@dataclass
class SeatOutcome:
    """What the aggregator needs to know about one seat."""

    seat_id: str
    status: str  # "ok" | "null" | "missing"
    score: SeatScore | None = None
    error: str | None = None
    calibrated: bool = True


@dataclass
class CouncilDecision:
    outcome: str
    valid_seats: list[str]
    null_seats: list[str]
    missing_seats: list[str]
    excluded_uncalibrated: list[str]
    pass_count: int
    tally: str
    council_overall_mean: float | None
    reduced_quorum: bool
    vetoes: dict[str, list[str]]
    reasons: list[str]
    rule: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_council(outcomes: Iterable[SeatOutcome], rule: QuorumRule, executor: Any = None) -> CouncilDecision:
    """Aggregate the seats.  ``executor`` is the ruling of the executor rule (EX-1) or ``None``.

    When the ruling carries a veto the outcome is VETO whatever the seats
    scored, and it is decided before quorum: no number of seats can approve a
    pack whose declared scenarios do not all pass.  With ``executor=None``
    (legacy recomputation: the 2026 JSON have no executor result) the function
    behaves exactly as it did before the rule existed.
    """
    by_id = {o.seat_id: o for o in outcomes}
    valid, null, missing, excluded = [], [], [], []
    for sid in rule.voting_seats:
        o = by_id.get(sid)
        if o is None or o.status == "missing":
            missing.append(sid)
        elif o.status != "ok" or o.score is None:
            null.append(sid)
        elif rule.exclude_uncalibrated and not o.calibrated:
            excluded.append(sid)
        else:
            valid.append(sid)
    scored = [by_id[s].score for s in valid]
    vetoes = {s: by_id[s].score.vetoes for s in valid if by_id[s].score.vetoes}
    pass_count = sum(1 for sc in scored if sc.verdict == PASS)
    mean = None
    if scored:
        mean = round2(sum(Fraction(str(sc.overall_exact)) for sc in scored) / len(scored))
    reasons: list[str] = []
    if executor is not None and getattr(executor, "veto", False):
        outcome = OUTCOME_VETO
        reasons.append(executor.veto_reason)
        if vetoes:
            reasons.append("veto by " + ", ".join(f"{s} ({'; '.join(v)})" for s, v in vetoes.items()))
            reasons.append("RUBRIC.md: 'The veto cannot be overridden by the Dean.'")
        if len(valid) < rule.min_valid_seats:
            reasons.append(f"quorum not reached either: {len(valid)} valid seat(s) < minimum {rule.min_valid_seats}")
        vetoes = {"executor": [executor.veto_short], **vetoes}
    elif len(valid) < rule.min_valid_seats:
        outcome = OUTCOME_NO_QUORUM
        reasons.append(
            f"{len(valid)} valid seat(s) < minimum {rule.min_valid_seats}"
            + (f"; null: {', '.join(null)}" if null else "")
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; excluded (failed decoy calibration): {', '.join(excluded)}" if excluded else "")
        )
    elif vetoes:
        outcome = OUTCOME_VETO
        reasons.append("veto by " + ", ".join(f"{s} ({'; '.join(v)})" for s, v in vetoes.items()))
        reasons.append("RUBRIC.md: 'The veto cannot be overridden by the Dean.'")
    elif any(sc.verdict == FAIL for sc in scored):
        outcome = OUTCOME_FAIL
        reasons.append("FAIL by " + ", ".join(s for s in valid if by_id[s].score.verdict == FAIL))
    elif any(sc.verdict == PASS_WITH_REVISIONS for sc in scored):
        outcome = OUTCOME_REVISIONS
        reasons.append(
            "revisions required by "
            + ", ".join(s for s in valid if by_id[s].score.verdict == PASS_WITH_REVISIONS)
        )
    elif pass_count >= rule.min_pass_seats and mean is not None and mean >= 7:
        outcome = OUTCOME_PASS
        reasons.append(f"{pass_count} PASS >= {rule.min_pass_seats}, council mean {mean} >= 7")
    else:  # pragma: no cover - unreachable with min_pass_seats <= min_valid_seats
        outcome = OUTCOME_REVISIONS
        reasons.append("insufficient PASS seats")
    reduced = len(valid) < len(rule.voting_seats)
    if reduced and outcome != OUTCOME_NO_QUORUM:
        reasons.append(f"reduced quorum: {len(valid)}/{len(rule.voting_seats)} voting seats valid")
    return CouncilDecision(
        outcome=outcome,
        valid_seats=valid,
        null_seats=null,
        missing_seats=missing,
        excluded_uncalibrated=excluded,
        pass_count=pass_count,
        tally=f"{pass_count}/{len(valid)}",
        council_overall_mean=mean,
        reduced_quorum=reduced,
        vetoes=vetoes,
        reasons=reasons,
        rule=asdict(rule),
    )
