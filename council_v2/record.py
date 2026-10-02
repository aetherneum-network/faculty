"""Seat records: one signed JSON per seat, including failed seats.

Council v2 rules 6 and 7 (review 2026-09-30 §3):
"Tracciabilità completa. ID modello dalla risposta, request-id, risposta
grezza, SHA-256 del bundle, SHA del commit, parametri. JSON firmato Ed25519"
and "Guasti dichiarati. Un seggio fallito produce un file null con il log".

Record kinds (field ``schema``):

* ``aetherneum.council-v2.seat-record/1``     one voting seat, ok or null
* ``aetherneum.council-v2.executor-record/1`` the non-voting executor seat
* ``aetherneum.council-v2.decision/1``        the aggregate, recomputable from the seat records
* ``aetherneum.council-v2.legacy-import/1``   a 2026 JSON re-scored by code (see legacy.py)

Records are append-only: ``write_signed`` refuses to overwrite a file.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import CRITERIA_ORDER, scoring
from .bundle import Bundle
from .seats import SeatResult, PROMPT_SHA256
from .signing import Ed25519Signer, VerifyResult, sign_record, verify_record

SEAT_SCHEMA = "aetherneum.council-v2.seat-record/1"
EXECUTOR_SCHEMA = "aetherneum.council-v2.executor-record/1"
DECISION_SCHEMA = "aetherneum.council-v2.decision/1"
LEGACY_SCHEMA = "aetherneum.council-v2.legacy-import/1"
SCORE_BEARING = (SEAT_SCHEMA, LEGACY_SCHEMA)


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_session(kind: str, *, dry_run: bool, mock: bool, council_config: Mapping[str, Any] | None = None,
                faculty_commit: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    cfg_sha = None
    if council_config is not None:
        cfg_sha = hashlib.sha256(json.dumps(council_config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return {
        "session_id": session_id or f"{stamp}-{kind}-{uuid.uuid4().hex[:8]}",
        "kind": kind,
        "started_at": now(),
        "dry_run": dry_run,
        "mock": mock,
        "council_config_sha256": cfg_sha,
        "faculty_commit": faculty_commit,
    }


def caps_to_dicts(caps: Iterable[scoring.Cap]) -> list[dict[str, Any]]:
    return [asdict(c) for c in caps]


def caps_from_dicts(items: Iterable[Mapping[str, Any]]) -> list[scoring.Cap]:
    return [scoring.Cap(i["criterion"], int(i["cap"]), i["reason"]) for i in items or []]


def build_seat_record(
    session: Mapping[str, Any],
    seat_cfg: Mapping[str, Any],
    result: SeatResult,
    bundle: Bundle,
    *,
    candidate: Mapping[str, Any],
    caps: Iterable[scoring.Cap] = (),
    calibration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    caps = list(caps)
    scored = scoring.score_seat(result.scores, caps).to_dict() if result.status == "ok" else None
    requested = result.model_requested
    got = result.model_from_response
    return {
        "schema": SEAT_SCHEMA,
        "session": dict(session),
        "candidate": dict(candidate),
        "seat": {
            "seat_id": result.seat_id,
            "role": seat_cfg.get("role"),
            "voting": bool(seat_cfg.get("voting", True)),
            "provider": result.provider,
        },
        "status": result.status,
        "model_requested": requested,
        "model_from_response": got,
        "model_source": "api_response.model" if got else None,
        "model_mismatch": bool(got and requested and got != requested),
        "request_id": result.request_id,
        "response_id": result.response_id,
        "params": result.params,
        "prompt_sha256": PROMPT_SHA256,
        "bundle_sha256": bundle.sha256,
        "bundle": bundle.manifest(),
        "faculty_commit": bundle.faculty_commit,
        "candidate_repo_head": (bundle.evidence_manifest.get("git") or {}).get("head_sha"),
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "output": result.output,  # the seat's structured output: 7 scores + rationales, no overall, no verdict
        "scores_raw": result.scores,
        "caps": caps_to_dicts(caps),
        "scoring": scored,  # computed by council_v2.scoring, never by the model
        "unresolved_citations": result.unresolved_citations,
        "usage": result.usage,
        "stop_reason": result.stop_reason,
        "stop_details": result.stop_details,
        "error": result.error,
        "log": result.log,
        "raw_response": result.raw_response,
        "calibration": dict(calibration) if calibration else {"status": "not_run"},
        "mock": result.mock,
        "dry_run": bool(session.get("dry_run")),
    }


def build_executor_record(session: Mapping[str, Any], candidate: Mapping[str, Any], executor_result: Mapping[str, Any] | None,
                          *, error: str | None = None, faculty_commit: str | None = None) -> dict[str, Any]:
    return {
        "schema": EXECUTOR_SCHEMA,
        "session": dict(session),
        "candidate": dict(candidate),
        "seat": {"seat_id": "executor", "role": "executor", "voting": False, "provider": "local-subprocess"},
        "status": "ok" if executor_result is not None and error is None else "null",
        "result": dict(executor_result) if executor_result is not None else None,
        "error": error,
        "faculty_commit": faculty_commit,
        "recorded_at": now(),
        "dry_run": bool(session.get("dry_run")),
    }


def seat_outcome_from_record(rec: Mapping[str, Any]) -> scoring.SeatOutcome:
    """Recompute a seat's scoring from its signed inputs (never trust 'scoring')."""
    sid = rec["seat"]["seat_id"]
    if rec.get("status") != "ok" or rec.get("scores_raw") is None:
        err = rec.get("error")
        msg = err.get("type") if isinstance(err, Mapping) else (str(err) if err else "null seat")
        return scoring.SeatOutcome(sid, "null", None, msg)
    sc = scoring.score_seat(rec["scores_raw"], caps_from_dicts(rec.get("caps", [])))
    cal = rec.get("calibration") or {}
    return scoring.SeatOutcome(sid, "ok", sc, None, calibrated=cal.get("status") != "failed")


def build_decision_record(session: Mapping[str, Any], candidate: Mapping[str, Any], seat_records: list[Mapping[str, Any]],
                          rule: scoring.QuorumRule, *, bundle_sha256: str | None) -> dict[str, Any]:
    outcomes = [seat_outcome_from_record(r) for r in seat_records if r["seat"].get("voting", True)]
    decision = scoring.decide_council(outcomes, rule)
    return {
        "schema": DECISION_SCHEMA,
        "session": dict(session),
        "candidate": dict(candidate),
        "bundle_sha256": bundle_sha256,
        "seat_files": sorted(f"{candidate['slug']}__{r['seat']['seat_id']}.json" for r in seat_records),
        "decision": decision.to_dict(),
        "interpretations": scoring.INTERPRETATIONS,
        "human_steps_pending": [
            "external human reviewer minutes (review §3 rule 8)",
            "written Patron approval minutes with criteria used",
            "appeal window and planned revocation date",
        ],
        "recorded_at": now(),
        "dry_run": bool(session.get("dry_run")),
    }


class RecordExists(FileExistsError):
    pass


def write_signed(record: dict[str, Any], path: str | Path, signer: Ed25519Signer) -> Path:
    """Sign and write; never overwrite (the ledger is append-only)."""
    p = Path(path)
    if p.exists():
        raise RecordExists(f"refusing to overwrite {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    signed = sign_record(record, signer)
    p.write_text(json.dumps(signed, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    return p


def record_filename(slug: str, seat_id: str) -> str:
    return f"{slug}__{seat_id}.json"


def load_records(paths: Iterable[str | Path], public_key: bytes) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Load every ``*.json`` under ``paths``; return (verified records, rejected [(file, reason)]).

    Each verified record gets a transient ``_file`` key (not part of the signature).
    """
    ok: list[dict[str, Any]] = []
    rejected: list[tuple[str, str]] = []
    for base in paths:
        base = Path(base)
        files = [base] if base.is_file() else sorted(base.rglob("*.json"))
        for f in files:
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                rejected.append((str(f), f"unreadable: {e}"))
                continue
            if not isinstance(rec, dict) or "schema" not in rec:
                rejected.append((str(f), "not a council-v2 record"))
                continue
            res: VerifyResult = verify_record(rec, public_key)
            if not res.ok:
                rejected.append((str(f), res.reason))
                continue
            rec["_file"] = f.name
            ok.append(rec)
    return ok, rejected


def scores_table(rec: Mapping[str, Any]) -> list[int] | None:
    s = rec.get("scores_raw")
    return None if s is None else [s[k] for k in CRITERIA_ORDER]
