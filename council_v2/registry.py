"""Generate the Registry table ONLY from signed Council records.

Council v2 rule 7 (review 2026-09-30 §3): "il Registry si genera dai JSON".

* Input: directories of signed records.  A record that does not verify
  against the configured public key is rejected and listed — it can never
  contribute a number.
* Every seat score shown is recomputed here from the record's own raw
  scores and caps; the record's stored ``scoring`` block is only compared,
  never trusted.  A seat with no record, or a null record, is shown as null
  with its error — never as "—" and never as a number.
* Dry-run and mock records are excluded unless ``include_mock=True``.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import scoring
from .record import SCORE_BEARING, LEGACY_SCHEMA, load_records, seat_outcome_from_record


def load_council(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def seat_order(council: Mapping[str, Any]) -> list[str]:
    return list(council["quorum"]["voting_seats"])


def legacy_map(council: Mapping[str, Any]) -> dict[str, str]:
    return {s["legacy_seat_id"]: s["seat_id"] for s in council["seats"] if s.get("legacy_seat_id")}


def seat_label(council: Mapping[str, Any], sid: str) -> str:
    for s in council["seats"]:
        if s["seat_id"] == sid:
            return s.get("role", sid)
    return sid


@dataclass
class RegistryRow:
    slug: str
    number: int | None
    name: str
    specialty: str | None
    session_id: str
    provenance: str
    decision: scoring.CouncilDecision
    seats: dict[str, dict[str, Any]]
    notes: list[str] = field(default_factory=list)
    sessions_seen: int = 1
    mock: bool = False  # True if any record of the session is mock or dry-run (only with include_mock)
    marker: str | None = None  # session marker (run_council_v2 --marker), e.g. a rehearsal notice


MOCK_PROVENANCE = "MOCK / DRY-RUN session — not a Council verdict"


def _seat_key(rec: Mapping[str, Any], voting: list[str], lmap: Mapping[str, str]) -> str:
    sid = rec["seat"]["seat_id"]
    if sid in voting:
        return sid
    return lmap.get(rec["seat"].get("legacy_seat_id") or sid, sid)


def _session_time(recs: list[Mapping[str, Any]]) -> str:
    s = recs[0]["session"]
    return s.get("started_at") or s.get("imported_at") or ""


def build_rows(records: Iterable[Mapping[str, Any]], council: Mapping[str, Any], *, include_mock: bool = False) -> list[RegistryRow]:
    voting = seat_order(council)
    lmap = legacy_map(council)
    by_cand: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
    for r in records:
        if r.get("schema") not in SCORE_BEARING:
            continue
        if r["candidate"].get("decoy") or r["session"].get("kind") == "calibration":
            continue  # decoys are calibration material, never Registry entries
        if not include_mock and (r.get("mock") or r.get("dry_run")):
            continue
        slug = r["candidate"]["slug"]
        by_cand.setdefault(slug, {}).setdefault(r["session"]["session_id"], []).append(r)
    rows: list[RegistryRow] = []
    for slug, sessions in by_cand.items():
        sid, recs = max(sessions.items(), key=lambda kv: _session_time(kv[1]))
        seats: dict[str, dict[str, Any]] = {}
        outcomes = []
        notes: list[str] = []
        for r in recs:
            key = _seat_key(r, voting, lmap)
            if not r["seat"].get("voting", True) or key not in voting:
                continue
            o = seat_outcome_from_record(r)
            o.seat_id = key
            outcomes.append(o)
            entry: dict[str, Any] = {"status": o.status, "file": r.get("_file")}
            if o.status == "ok":
                entry.update({"overall": o.score.overall, "verdict": o.score.verdict, "vetoes": o.score.vetoes,
                              "caps": o.score.caps_applied})
                stored = (r.get("scoring") or {})
                if stored and (stored.get("overall") != o.score.overall or stored.get("verdict") != o.score.verdict):
                    notes.append(f"{key}: stored scoring differs from recomputation (stored {stored.get('overall')}/{stored.get('verdict')})")
                if r.get("schema") == LEGACY_SCHEMA and r.get("recorded"):
                    entry["recorded_overall"] = r["recorded"].get("overall_score")
                    entry["recorded_verdict"] = r["recorded"].get("verdict")
            else:
                err = r.get("error") or {}
                entry["error"] = err.get("type") if isinstance(err, Mapping) else str(err)
            seats[key] = entry
        for key in voting:
            if key not in seats:
                seats[key] = {"status": "missing", "error": "no record"}
        decision = scoring.decide_council(outcomes, scoring.QuorumRule(voting_seats=tuple(voting)))
        cand: dict[str, Any] = {}
        for r in recs:  # first non-empty value per key (null seat records may carry less)
            for k, v in r["candidate"].items():
                if v is not None and cand.get(k) is None:
                    cand[k] = v
        legacy = recs[0].get("schema") == LEGACY_SCHEMA
        # A mock or dry-run session can reach this point only with include_mock=True.
        # It must never read like a Council verdict: the row says what it is.
        is_mock = any(r.get("mock") or r.get("dry_run") or r["session"].get("mock") or r["session"].get("dry_run") for r in recs)
        marker = next((r["session"].get("marker") for r in recs if r["session"].get("marker")), None)
        if is_mock:
            provenance = MOCK_PROVENANCE + (f" · {marker}" if marker else "")
        elif legacy:
            provenance = "legacy 2026 JSON, re-scored by code (origin unsigned)"
        else:
            provenance = "Council v2 session, signed at run"
        rows.append(RegistryRow(
            slug=slug,
            number=cand.get("number"),
            name=cand.get("name") or slug,
            specialty=cand.get("specialty"),
            session_id=sid,
            provenance=provenance,
            decision=decision,
            seats=seats,
            notes=notes,
            sessions_seen=len(sessions),
            mock=is_mock,
            marker=marker,
        ))
    rows.sort(key=lambda r: (r.number is None, r.number or 0, r.slug))
    return rows


def _seat_cell(e: Mapping[str, Any]) -> str:
    if e["status"] == "ok":
        s = f"{e['overall']:.2f} {e['verdict']}"
        if e.get("recorded_overall") is not None and abs(float(e["recorded_overall"]) - e["overall"]) >= 0.005:
            s += f" (model wrote {e['recorded_overall']})"
        return s
    return f"null ({e.get('error') or e['status']})"


def tally_text(d: scoring.CouncilDecision, n_voting: int) -> str:
    t = f"{d.tally} PASS"
    extra = []
    if d.null_seats:
        extra.append(f"{len(d.null_seats)} null")
    if d.missing_seats:
        extra.append(f"{len(d.missing_seats)} missing")
    if d.excluded_uncalibrated:
        extra.append(f"{len(d.excluded_uncalibrated)} excluded (decoy)")
    if d.reduced_quorum and d.outcome != scoring.OUTCOME_NO_QUORUM:
        extra.append(f"reduced quorum {len(d.valid_seats)}/{n_voting}")
    return t + (" · " + ", ".join(extra) if extra else "")


def mock_banner(rows: list[RegistryRow]) -> str | None:
    """One visible line for a table that contains mock / dry-run rows (None if it has none)."""
    mock_rows = [r for r in rows if r.mock]
    if not mock_rows:
        return None
    markers = sorted({r.marker for r in mock_rows if r.marker})
    label = " / ".join(markers) if markers else MOCK_PROVENANCE
    return f"{label} ({len(mock_rows)} of {len(rows)} row(s) are mock or dry-run: never for publication)"


def to_markdown(rows: list[RegistryRow], council: Mapping[str, Any], rejected: list[tuple[str, str]] = ()) -> str:
    voting = seat_order(council)
    head = ["#", "Alumnus", "Master of the Æther in", "Council (rule-based)", "Outcome"] + [seat_label(council, s) for s in voting] + ["Vetoes", "Provenance"]
    out = ["<!-- GENERATED by scripts/build_registry.py from signed records only. Do not edit by hand. -->", ""]
    banner = mock_banner(rows)
    if banner:
        out += [f"> **{banner}**", ""]
    out += [
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
    ]
    for r in rows:
        vetoes = "; ".join(f"{s}: {', '.join(v)}" for s, v in r.decision.vetoes.items()) or "—"
        cells = [f"{r.number:02d}" if r.number else "", r.name, r.specialty or "", tally_text(r.decision, len(voting)), r.decision.outcome]
        cells += [_seat_cell(r.seats[s]) for s in voting]
        cells += [vetoes, r.provenance]
        out.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    out += [
        "",
        "Scores are weighted overalls recomputed by `council_v2.scoring` from each record's seven raw scores "
        "(admission/RUBRIC.md weights, thresholds and vetoes). 'null' = the seat produced no valid result; "
        "it counts as absent, never as a PASS.",
    ]
    notes = [f"- {r.name}: {n}" for r in rows for n in r.notes]
    if notes:
        out += ["", "Notes:", *notes]
    if rejected:
        out += ["", f"Rejected files ({len(rejected)}): signature missing or invalid — not shown above."]
        out += [f"- `{Path(f).name}`: {why}" for f, why in rejected]
    return "\n".join(out) + "\n"


def to_html(rows: list[RegistryRow], council: Mapping[str, Any]) -> str:
    voting = seat_order(council)
    e = html.escape
    th = "".join(f"<th>{e(h)}</th>" for h in ["#", "Alumnus", "Master of the Æther in", "Council", "Outcome"]
                 + [seat_label(council, s) for s in voting] + ["Vetoes", "Provenance"])
    body = []
    for r in rows:
        vetoes = "; ".join(f"{s}: {', '.join(v)}" for s, v in r.decision.vetoes.items()) or "—"
        tds = [f"{r.number:02d}" if r.number else "", r.name, r.specialty or "", tally_text(r.decision, len(voting)), r.decision.outcome]
        tds += [_seat_cell(r.seats[s]) for s in voting] + [vetoes, r.provenance]
        cls = r.decision.outcome.lower().replace("_", "-") + (" registry-mock" if r.mock else "")
        body.append(f'<tr class="outcome-{cls}" data-slug="{e(r.slug)}">' + "".join(f"<td>{e(str(t))}</td>" for t in tds) + "</tr>")
    banner = mock_banner(rows)
    return (
        "<!-- GENERATED by scripts/build_registry.py from signed records only. Do not edit by hand. -->\n"
        + (f'<p class="registry-mock-banner"><strong>{e(banner)}</strong></p>\n' if banner else "")
        + '<table class="registry-v2">\n<thead><tr>' + th + "</tr></thead>\n<tbody>\n" + "\n".join(body) + "\n</tbody>\n</table>\n"
    )


def build(record_dirs: Iterable[str | Path], public_key: bytes, council: Mapping[str, Any], *, include_mock: bool = False):
    records, rejected = load_records(record_dirs, public_key)
    rows = build_rows(records, council, include_mock=include_mock)
    return rows, rejected
