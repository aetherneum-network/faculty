"""Re-score the 2026 Council JSONs with the deterministic rubric.

This is analysis, not a new defense.  The legacy JSONs keep their own
numbers; ``legacy_records`` wraps each one in a ``legacy-import`` record that
states exactly what is and is not known about it:

* scores: as recorded by the model;
* overall / verdict: recorded by the model AND recomputed by
  ``council_v2.scoring`` (both kept, discrepancies listed);
* model: ``model_self_reported`` only — the 2026 orchestrators stored no API
  response, so ``model_from_response`` is null;
* request id, raw response, parameters, bundle hash, run-time commit:
  null, and listed under ``missing_provenance``;
* a seat that wrote no file becomes an explicit ``null`` record whose error
  says so — the 2026 orchestrators discarded failed seats, which is how the
  Registry came to show scores that exist in no JSON.

A signature on a legacy-import record attests only "this file, with this
SHA-256, existed at this faculty commit and re-scores to these numbers".  It
does not attest the 2026 review itself.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import CRITERIA_ORDER, scoring
from .bundle import git_blobs
from .record import LEGACY_SCHEMA, now

LEGACY_SEATS = ("anthropic_chair", "cerebras_reasoning", "moonshot_longctx", "groq_velocity")
LEGACY_PROVIDER = {
    "anthropic_chair": "anthropic", "cerebras_reasoning": "cerebras",
    "moonshot_longctx": "moonshot", "groq_velocity": "groq",
}
COHORTS = {
    "cohort-phase-0": "phase-0 (retroactive, 2026-05-14)",
    "cohort-q2-2026": "q2-2026",
}
MISSING_PROVENANCE = [
    "model id from the API response (only the self-reported reviewer_model exists)",
    "request id",
    "raw API response",
    "request parameters (temperature, max_tokens, bundle variant)",
    "SHA-256 of the bundle sent",
    "faculty commit SHA at run time",
    "signature at run time",
]
# Causes stated in alumni/_ROSTER.md for seats that produced no JSON.
ROSTER_CLAIMED_CAUSE = {
    ("ezio-cardone", "cerebras_reasoning"): "_ROSTER.md 2026-05-19: 'transient failure (Cerebras 429 / Anthropic JSON)' — no JSON written",
    ("adele-maurique", "anthropic_chair"): "_ROSTER.md 2026-05-19: 'transient failure (Cerebras 429 / Anthropic JSON)' — no JSON written",
    ("tomaso-riviera", "anthropic_chair"): "_ROSTER.md 2026-05-20: 'Anthropic Chair hit transient JSON parse error' — no JSON written",
}


def _git(root: Path, *args: str) -> str | None:
    try:
        cp = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return cp.stdout.strip() if cp.returncode == 0 else None


def _last_commits(root: Path, rel_dir: str) -> dict[str, str]:
    """{path: latest commit touching it} for every file under ``rel_dir``, in one git call."""
    out = _git(root, "log", "--format=@%H", "--name-only", "--", rel_dir) or ""
    last: dict[str, str] = {}
    sha = None
    for line in out.splitlines():
        if line.startswith("@"):
            sha = line[1:]
        elif line.strip() and sha and line.strip() not in last:
            last[line.strip()] = sha
    return last


def load_cohort(faculty_root: Path, cohort_dir: str) -> dict[str, dict[str, tuple[Path, dict[str, Any]]]]:
    """{slug: {legacy_seat_id: (path, json)}} for one cohort directory."""
    out: dict[str, dict[str, tuple[Path, dict[str, Any]]]] = {}
    for f in sorted((faculty_root / cohort_dir / "council-reviews").glob("*.json")):
        slug, _, seat = f.stem.partition("__")
        out.setdefault(slug, {})[seat] = (f, json.loads(f.read_text(encoding="utf-8")))
    return out


def rescore(review: Mapping[str, Any], caps: Iterable[scoring.Cap] = ()) -> dict[str, Any]:
    """Recompute one legacy review.  Returns recorded vs computed side by side."""
    sc = scoring.score_seat(review["criterion_scores"], caps)
    rec_overall = review.get("overall_score")
    rec_verdict = review.get("verdict")
    disc = []
    if rec_overall is None or abs(float(rec_overall) - sc.overall) >= 0.005:
        disc.append(f"overall recorded {rec_overall} vs computed {sc.overall}")
    if rec_verdict != sc.verdict:
        disc.append(f"verdict recorded {rec_verdict} vs rule-based {sc.verdict}")
    return {"scoring": sc, "recorded_overall": rec_overall, "recorded_verdict": rec_verdict, "discrepancies": disc}


def legacy_records(faculty_root: Path, cohort_dir: str, *, candidates: Mapping[str, Mapping[str, Any]] | None = None,
                   seats: Iterable[str] = LEGACY_SEATS, v2_seat_map: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Build unsigned legacy-import records (one per expected seat, null if no file)."""
    root = Path(faculty_root).resolve()
    commit = _git(root, "rev-parse", "HEAD")
    data = load_cohort(root, cohort_dir)
    reviews_dir = f"{cohort_dir}/council-reviews"
    blobs = git_blobs(root, [reviews_dir])
    last = _last_commits(root, reviews_dir)
    session = {
        "session_id": f"legacy-{cohort_dir}",
        "kind": "legacy-import",
        "imported_at": now(),
        "faculty_commit": commit,
        "dry_run": False,
        "mock": False,
        "cohort": COHORTS.get(cohort_dir, cohort_dir),
    }
    v2_seat_map = v2_seat_map or {}
    out = []
    for slug in sorted(data):
        cand_info = dict((candidates or {}).get(slug, {}))
        for seat in seats:
            entry = data[slug].get(seat)
            base = {
                "schema": LEGACY_SCHEMA,
                "session": session,
                "candidate": {"slug": slug, **{k: v for k, v in cand_info.items() if k in ("name", "specialty", "number", "cohort")}},
                "seat": {"seat_id": v2_seat_map.get(seat, seat), "legacy_seat_id": seat, "voting": True,
                         "provider": LEGACY_PROVIDER.get(seat, "unknown")},
                "provenance": "legacy unsigned JSON (2026); scores as recorded, overall and verdict recomputed by council_v2.scoring",
                "model_requested": None,
                "model_from_response": None,
                "request_id": None,
                "response_id": None,
                "bundle_sha256": None,
                "missing_provenance": MISSING_PROVENANCE,
                "caps": [],
                "calibration": {"status": "not_run"},
                "mock": False,
                "dry_run": False,
            }
            if entry is None:
                base.update({
                    "status": "null",
                    "source_file": None,
                    "scores_raw": None,
                    "scoring": None,
                    "error": {"type": "no_file", "message": "no JSON was written for this seat; the 2026 orchestrator discarded failed seats",
                              "claimed_cause": ROSTER_CLAIMED_CAUSE.get((slug, seat))},
                })
                out.append(base)
                continue
            path, review = entry
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            rs = rescore(review)
            if "specialty" not in base["candidate"]:
                base["candidate"]["specialty"] = review.get("candidate_specialty")
            base.update({
                "status": "ok",
                "source_file": rel,
                "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "source_git_blob": blobs.get(rel),
                "source_last_commit": last.get(rel),
                "model_self_reported": review.get("reviewer_model"),
                "review_date_recorded": review.get("review_date"),
                "scores_raw": {k: review["criterion_scores"][k]["score"] for k in CRITERIA_ORDER},
                "scoring": rs["scoring"].to_dict(),
                "recorded": {
                    "overall_score": rs["recorded_overall"],
                    "verdict": rs["recorded_verdict"],
                    "veto_applied": review.get("veto_applied"),
                    "revisions_required": review.get("revisions_required", []),
                    "dissent": review.get("dissent"),
                },
                "discrepancies": rs["discrepancies"],
                "error": None,
            })
            out.append(base)
    return out


def identical_vectors(records: Iterable[Mapping[str, Any]], min_candidates: int = 3) -> list[dict[str, Any]]:
    """Seats that gave the same 7-score vector to >= ``min_candidates`` different candidates."""
    groups: dict[tuple[str, tuple[int, ...]], set[str]] = {}
    for r in records:
        if r.get("scores_raw") is None:
            continue
        vec = tuple(r["scores_raw"][k] for k in CRITERIA_ORDER)
        sid = r["seat"].get("legacy_seat_id") or r["seat"]["seat_id"]
        groups.setdefault((sid, vec), set()).add(r["candidate"]["slug"])
    out = []
    for (sid, vec), slugs in sorted(groups.items()):
        if len(slugs) >= min_candidates:
            out.append({"seat": sid, "vector": list(vec), "candidates": sorted(slugs)})
    return out
