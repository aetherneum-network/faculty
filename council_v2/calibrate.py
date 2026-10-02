"""Decoy calibration: flag any seat that passes a deliberately weak candidate.

Council v2 rule 4 (review 2026-09-30 §3): "Candidati civetta. Ogni sessione
include un profilo noto come debole. Un seggio che lo promuove viene ritarato
o sostituito."

* The decoys live in ``council_v2/decoys/<slug>/`` (intake.md, profile.md,
  repo/, expected.json).  Their intakes are neutral: they must pass
  ``lint_intake`` like any real intake.
* A seat is judged on its RAW scores, before evidence caps.  The evidence cap
  (zero artifacts => body_of_work <= 3) would veto every decoy automatically
  and hide a lenient seat; calibration asks what the seat itself concluded.
* A seat FAILS calibration if, on any decoy, its rule-based verdict is PASS
  or PASS_WITH_REVISIONS, or its raw weighted overall is >= 7.  A seat with
  no valid result on a decoy is NOT calibrated (it cannot vote either).
* ``identical_vectors`` additionally flags a seat that gives the same
  seven-score vector to 3+ different candidates (the 2026 Groq pattern).

Decoys published in this repository are known to anyone who reads it.  For
the real re-defense rotate them: keep the session's decoys private until the
session's records are published (see README.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import scoring
from .bundle import build_bundle
from .evidence import scan_repo
from .seats import Seat, SeatResult

DECOYS_DIR = Path(__file__).resolve().parent / "decoys"
FORBIDDEN = (scoring.PASS, scoring.PASS_WITH_REVISIONS)


@dataclass
class Decoy:
    slug: str
    intake: Path
    profile: Path
    repo: Path
    expected: dict[str, Any]


def load_decoys(root: Path = DECOYS_DIR) -> list[Decoy]:
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        exp = d / "expected.json"
        if not exp.exists():
            continue
        out.append(Decoy(d.name, d / "intake.md", d / "profile.md", d / "repo", json.loads(exp.read_text(encoding="utf-8"))))
    return out


@dataclass
class SeatCalibration:
    seat_id: str
    status: str  # "passed" | "failed"
    decoys: dict[str, dict[str, Any]] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


@dataclass
class CalibrationReport:
    seats: dict[str, SeatCalibration]
    decoys: list[str]

    @property
    def failed(self) -> list[str]:
        return [s for s, c in self.seats.items() if c.status == "failed"]

    def status_for(self, seat_id: str) -> dict[str, Any]:
        c = self.seats.get(seat_id)
        if c is None:
            return {"status": "not_run"}
        return {"status": c.status, "decoys": c.decoys, "reasons": c.reasons}

    def to_dict(self) -> dict[str, Any]:
        return {"decoys": self.decoys, "failed": self.failed, "seats": {k: asdict(v) for k, v in self.seats.items()}}


def judge(results: Mapping[str, Mapping[str, SeatResult | Mapping[str, int] | None]], decoys: Iterable[str]) -> CalibrationReport:
    """``results[seat_id][decoy_slug]`` is a SeatResult, a raw score dict, or None."""
    decoys = list(decoys)
    report: dict[str, SeatCalibration] = {}
    for seat_id, per in results.items():
        cal = SeatCalibration(seat_id, "passed")
        for d in decoys:
            r = per.get(d)
            scores = r.scores if isinstance(r, SeatResult) else r
            if isinstance(r, SeatResult) and r.status != "ok":
                scores = None
            if not scores:
                cal.status = "failed"
                cal.reasons.append(f"{d}: no valid result — seat cannot be calibrated")
                cal.decoys[d] = {"status": "null"}
                continue
            sc = scoring.score_seat(scores)  # RAW: no evidence caps
            cal.decoys[d] = {"raw_overall": sc.overall, "raw_verdict": sc.verdict, "scores": sc.scores_raw}
            if sc.verdict in FORBIDDEN:
                cal.status = "failed"
                cal.reasons.append(f"{d}: raw verdict {sc.verdict} (overall {sc.overall}) on a known-weak decoy")
            elif sc.overall >= 7:
                cal.status = "failed"
                cal.reasons.append(f"{d}: raw overall {sc.overall} >= 7 on a known-weak decoy")
        report[seat_id] = cal
    return CalibrationReport(report, decoys)


def run_calibration(seats: Iterable[Seat], *, faculty_root: Path, decoys: list[Decoy] | None = None):
    """Score every decoy with every seat (same bundle for all seats per decoy).

    Returns ``(report, results[seat_id][decoy_slug], bundles[decoy_slug])``.
    """
    decoys = decoys if decoys is not None else load_decoys()
    seats = list(seats)
    results: dict[str, dict[str, SeatResult]] = {s.seat_id: {} for s in seats}
    bundles = {}
    for d in decoys:
        bundle = build_bundle(d.slug, faculty_root=faculty_root, intake_path=d.intake, profile_path=d.profile,
                              evidence_manifest=scan_repo(d.repo, with_git=False))
        bundles[d.slug] = bundle
        for s in seats:
            results[s.seat_id][d.slug] = s.score(bundle)
    return judge(results, [d.slug for d in decoys]), results, bundles


def _main(argv: list[str] | None = None) -> int:  # pragma: no cover - demo CLI
    import argparse
    import sys

    from .seats import MockSeat

    ap = argparse.ArgumentParser(description="Decoy calibration drill (mock seats, offline)")
    ap.add_argument("--faculty-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    strict = {"body_of_work_depth": 2, "specialty_uniqueness": 3, "voice_personality_clarity": 3, "faithful_distillation": 2,
              "synthetic_transparency": 6, "placement_fit": 2, "continuity_with_class": 4}
    lenient = {"body_of_work_depth": 8, "specialty_uniqueness": 9, "voice_personality_clarity": 8, "faithful_distillation": 9,
               "synthetic_transparency": 10, "placement_fit": 9, "continuity_with_class": 8}
    seats = [MockSeat("anthropic", scores=strict), MockSeat("reasoning", scores=strict),
             MockSeat("longctx", scores=strict), MockSeat("velocity", scores=lenient)]
    rep, _, _ = run_calibration(seats, faculty_root=args.faculty_root)
    print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
    return 1 if rep.failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
