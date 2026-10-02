#!/usr/bin/env python3
"""Council v2 orchestrator: lint -> bundle -> calibration -> seats -> scoring -> signed records -> summary.

Default mode is ``--dry-run --mock``: no network, mock seats, an ephemeral
signing key, output under ``council_v2/out/<session>/`` (git-ignored).  It
exercises every step with the real bundle of the candidate, so a dry run
shows what the evidence cap and the vetoes would do today.

Live mode costs money and needs the Rector's approval.  All of these are
required, or the run refuses to start:

* ``--live`` (and not ``--mock``)
* environment ``AETHERNEUM_COUNCIL_LIVE=1`` plus the providers' API keys
* ``--key <private key file>`` (the production signing key; no ephemeral key)
* ``--approval-ref "<minutes id>"`` (recorded in every record's session block)

Seats whose provider/model is still ``[TO CONFIRM]`` in council/council.json
produce null records (and may break quorum) — by design.

Examples::

    python -m council_v2.run_council_v2 --slug costanza-notari
    python -m council_v2.run_council_v2 --slug costanza-notari --mock-fail-seat velocity
    python -m council_v2.run_council_v2 --slug costanza-notari --mock-lenient-seat velocity
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

FACULTY = Path(__file__).resolve().parents[1]
if str(FACULTY) not in sys.path:
    sys.path.insert(0, str(FACULTY))

from council_v2 import CRITERIA_ORDER, scoring  # noqa: E402
from council_v2.bundle import SteeringError, blocking, build_bundle, git_head, lint_intake  # noqa: E402
from council_v2.calibrate import load_decoys, run_calibration  # noqa: E402
from council_v2.evidence import scan_repo  # noqa: E402
from council_v2.executor import run_scenarios  # noqa: E402
from council_v2.record import (  # noqa: E402
    build_decision_record, build_executor_record, build_seat_record, new_session, record_filename, write_signed,
)
from council_v2.seats import LIVE_ENV, AnthropicSeat, MockSeat, OpenAICompatibleSeat  # noqa: E402
from council_v2.signing import Ed25519Signer, load_signer  # noqa: E402

DEFAULT_MOCK_VECTOR = (8, 8, 8, 8, 10, 7, 8)
DECOY_LOW = (2, 3, 3, 2, 6, 2, 4)


class RunRefused(RuntimeError):
    pass


def load_json(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _vec(v) -> dict[str, int]:
    return dict(zip(CRITERIA_ORDER, (int(x) for x in v)))


def build_mock_seats(council: dict[str, Any], *, vector=DEFAULT_MOCK_VECTOR, fail_seat: str | None = None,
                     lenient_seat: str | None = None) -> list[MockSeat]:
    decoys = {d.slug for d in load_decoys()}
    seats = []
    for sid in council["quorum"]["voting_seats"]:
        def scorer(bundle, sid=sid):
            if bundle.candidate_slug in decoys and sid != lenient_seat:
                return _vec(DECOY_LOW)
            return _vec(vector)
        seats.append(MockSeat(sid, provider="mock", scores=scorer, model=f"mock-{sid}",
                              fail=("mock failure: seat unavailable" if sid == fail_seat else None)))
    return seats


def build_live_seats(council: dict[str, Any], *, anthropic_client=None) -> list[Any]:
    seats = []
    for cfg in council["seats"]:
        if not cfg.get("voting"):
            continue
        if cfg["provider"] == "anthropic":
            p = cfg.get("params", {})
            seats.append(AnthropicSeat(cfg["seat_id"], model=cfg["model_planned"], effort=p.get("effort", "high"),
                                       max_tokens=int(p.get("max_tokens", 16000)), client=anthropic_client, allow_live=True))
        else:
            p = cfg.get("params", {})
            temp = p.get("temperature")
            seats.append(OpenAICompatibleSeat(
                cfg["seat_id"], cfg["provider"], endpoint=cfg.get("endpoint", "[TO CONFIRM]"),
                model=cfg.get("model_planned", "[TO CONFIRM]"), api_key_env=cfg.get("api_key_env", "[TO CONFIRM]"),
                temperature=temp if isinstance(temp, (int, float)) else None,
                max_tokens=int(p.get("max_tokens", 8000)), allow_live=True,
            ))
    return seats


def default_inputs(slug: str, repos_root: Path) -> dict[str, Path | None]:
    intake = FACULTY / "cohort-q2-2026" / "intake" / f"{slug}.md"
    pending = FACULTY / "alumni" / "pending" / f"{slug}.md"
    readme = repos_root / slug / "README.md"
    return {
        "intake": intake if intake.exists() else None,
        "profile": pending if pending.exists() else readme,
        "repo": repos_root / slug,
    }


def run(slug: str, *, repos_root: Path, out_root: Path, signer: Ed25519Signer, seats: list[Any], dry_run: bool,
        mock: bool, intake: Path | None, profile: Path, repo: Path | None, allow_steering: bool = False,
        run_executor: bool = True, with_calibration: bool = True, approval_ref: str | None = None,
        council_path: Path = FACULTY / "council" / "council.json", alumni_path: Path = FACULTY / "alumni" / "alumni.json") -> dict[str, Any]:
    council = load_json(council_path)
    alumni = {a["slug"]: a for a in load_json(alumni_path)["alumni"]} if alumni_path.exists() else {}
    a = alumni.get(slug, {})
    candidate = {
        "slug": slug,
        "name": (a.get("name") or {}).get("canonical") or slug,
        "specialty": (a.get("specialty") or {}).get("poetic_name"),
        "number": a.get("number"),
        "cohort": a.get("cohort"),
    }
    session = new_session("dry-run" if dry_run else "defense", dry_run=dry_run, mock=mock, council_config=council,
                          faculty_commit=git_head(FACULTY))
    session["approval_ref"] = approval_ref
    session["signing_key_id"] = signer.key_id
    out = out_root / session["session_id"]
    out.mkdir(parents=True, exist_ok=False)

    # 1. lint (blocks the run before any seat is called)
    findings = (lint_intake(intake) if intake else []) + lint_intake(profile)
    if blocking(findings) and not allow_steering:
        rec = {"schema": "aetherneum.council-v2.lint-block/1", "session": session, "candidate": candidate,
               "outcome": "BLOCKED_BY_LINT",
               "findings": [f.__dict__ for f in blocking(findings)], "dry_run": dry_run}
        write_signed(rec, out / f"{slug}__LINT_BLOCKED.json", signer)
        raise SteeringError(blocking(findings))

    # 2. evidence + executor
    manifest = scan_repo(repo) if repo else None
    exec_result = None
    exec_error = None
    if run_executor and repo and manifest and manifest.get("has_scenarios"):
        try:
            exec_result = run_scenarios(repo, head_sha=(manifest.get("git") or {}).get("head_sha")).to_dict()
        except Exception as e:  # noqa: BLE001 - recorded as a null executor record
            exec_error = f"{type(e).__name__}: {e}"
    if run_executor:
        write_signed(build_executor_record(session, candidate, exec_result, error=exec_error or (
            None if exec_result is not None else "no scenarios/ directory: nothing to execute"), faculty_commit=session["faculty_commit"]),
            out / record_filename(slug, "executor"), signer)

    # 3. bundle (identical for every seat)
    bundle = build_bundle(slug, faculty_root=FACULTY, intake_path=intake, profile_path=profile,
                          evidence_manifest=manifest, executor_result=exec_result, allow_steering=allow_steering)

    # 4. calibration on decoys, same seats, same session
    calibration = None
    if with_calibration:
        calibration, decoy_results, decoy_bundles = run_calibration(seats, faculty_root=FACULTY)
        cal_dir = out / "_calibration"
        for sid, per in decoy_results.items():
            for dslug, res in per.items():
                cfg = next((c for c in council["seats"] if c["seat_id"] == sid), {"role": sid, "voting": True})
                rec = build_seat_record({**session, "kind": "calibration"}, cfg, res, decoy_bundles[dslug],
                                        candidate={"slug": dslug, "decoy": True}, caps=[])
                write_signed(rec, cal_dir / record_filename(dslug, sid), signer)
        write_signed({"schema": "aetherneum.council-v2.calibration/1", "session": session, **calibration.to_dict()},
                     cal_dir / "CALIBRATION.json", signer)

    # 5. seats -> scoring -> records
    caps = scoring.evidence_caps(manifest)
    seat_records = []
    for seat in seats:
        res = seat.score(bundle)
        cfg = next((c for c in council["seats"] if c["seat_id"] == seat.seat_id), {"role": seat.seat_id, "voting": True})
        cal = calibration.status_for(seat.seat_id) if calibration else None
        rec = build_seat_record(session, cfg, res, bundle, candidate=candidate, caps=caps, calibration=cal)
        write_signed(rec, out / record_filename(slug, seat.seat_id), signer)
        seat_records.append(rec)

    # 6. decision, recomputed from the records just written
    rule = scoring.QuorumRule(voting_seats=tuple(council["quorum"]["voting_seats"]),
                              min_valid_seats=int(council["quorum"]["min_valid_seats"]),
                              min_pass_seats=int(council["quorum"]["min_pass_seats"]),
                              exclude_uncalibrated=bool(council["quorum"]["exclude_uncalibrated_seats"]))
    decision = build_decision_record(session, candidate, seat_records, rule, bundle_sha256=bundle.sha256)
    write_signed(decision, out / f"{slug}__DECISION.json", signer)
    return {"out": str(out), "session": session, "bundle_sha256": bundle.sha256, "decision": decision["decision"],
            "calibration_failed": calibration.failed if calibration else None, "caps": [c.__dict__ for c in caps],
            "lint_warnings": [f.__dict__ for f in findings if f.severity == "warn"],
            "seats": {r["seat"]["seat_id"]: {"status": r["status"], "model_from_response": r["model_from_response"],
                                             "overall": (r["scoring"] or {}).get("overall"), "verdict": (r["scoring"] or {}).get("verdict"),
                                             "error": (r["error"] or {}).get("type") if r["error"] else None} for r in seat_records}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--slug", required=True)
    ap.add_argument("--intake", type=Path)
    ap.add_argument("--no-intake", action="store_true", help="do not include an intake (profile + evidence only)")
    ap.add_argument("--profile", type=Path)
    ap.add_argument("--repo", type=Path)
    ap.add_argument("--repos-root", type=Path, default=FACULTY.parent)
    ap.add_argument("--out", type=Path, default=FACULTY / "council_v2" / "out")
    ap.add_argument("--live", action="store_true", help="call real providers (costs money; needs approval)")
    ap.add_argument("--mock", action="store_true", default=None, help="mock seats (default unless --live)")
    ap.add_argument("--key", type=Path, help="private signing key file (required with --live)")
    ap.add_argument("--approval-ref", help="Rector approval minutes reference (required with --live)")
    ap.add_argument("--allow-steering", action="store_true", help="dry-run only: continue despite lint block findings")
    ap.add_argument("--no-executor", action="store_true")
    ap.add_argument("--no-calibration", action="store_true")
    ap.add_argument("--mock-scores", help="comma-separated 7 scores for mock seats")
    ap.add_argument("--mock-fail-seat", help="make this mock seat fail (null record demo)")
    ap.add_argument("--mock-lenient-seat", help="this mock seat passes decoys (calibration demo)")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass

    live = bool(args.live)
    mock = (not live) if args.mock is None else bool(args.mock)
    if live and mock:
        print("refused: --live and --mock are exclusive", file=sys.stderr)
        return 2
    if live:
        missing = [n for n, ok in (("--key", args.key), ("--approval-ref", args.approval_ref),
                                   (f"{LIVE_ENV}=1", os.environ.get(LIVE_ENV) == "1")) if not ok]
        if missing:
            print(f"refused: live run needs {', '.join(missing)} (it costs money and requires the Rector's approval)", file=sys.stderr)
            return 2
        if args.allow_steering:
            print("refused: --allow-steering is not allowed in a live run", file=sys.stderr)
            return 2
    council = load_json(FACULTY / "council" / "council.json")
    inputs = default_inputs(args.slug, args.repos_root.resolve())
    intake = None if args.no_intake else (args.intake or inputs["intake"])
    profile = args.profile or inputs["profile"]
    repo = args.repo or inputs["repo"]

    if args.key:
        signer = load_signer(args.key)
    else:
        signer = Ed25519Signer.generate(label="ephemeral-dry-run")
    if mock:
        vec = tuple(int(x) for x in args.mock_scores.split(",")) if args.mock_scores else DEFAULT_MOCK_VECTOR
        seats = build_mock_seats(council, vector=vec, fail_seat=args.mock_fail_seat, lenient_seat=args.mock_lenient_seat)
    else:
        seats = build_live_seats(council)
    try:
        summary = run(args.slug, repos_root=args.repos_root.resolve(), out_root=args.out, signer=signer, seats=seats,
                      dry_run=not live, mock=mock, intake=intake, profile=profile, repo=repo,
                      allow_steering=args.allow_steering and not live, run_executor=not args.no_executor,
                      with_calibration=not args.no_calibration, approval_ref=args.approval_ref)
    except SteeringError as e:
        print(str(e), file=sys.stderr)
        print("run blocked: rewrite the intake without expected-score sentences (a signed LINT_BLOCKED record was written)", file=sys.stderr)
        return 3
    if not args.key:
        pub = Path(summary["out"]) / "ephemeral_public_key.pub"
        write_public_key_only(signer, pub)
        summary["public_key"] = str(pub)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def write_public_key_only(signer: Ed25519Signer, path: Path) -> None:
    """Write only the public key of an ephemeral signer (its seed is discarded)."""
    path.write_text(f"# EPHEMERAL dry-run key — not a Council key. key_id: {signer.key_id}\n{signer.public_key.hex()}\n",
                    encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
