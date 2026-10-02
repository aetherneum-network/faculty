#!/usr/bin/env python3
"""Re-score the 2026 Council JSONs (Q2 and Phase 0) with the deterministic rubric.

Writes ``council_v2/recomputed_2026-09-30.md``.  This is ANALYSIS, not a new
defense: the seven scores are the 2026 model outputs on prose, unchanged;
only the arithmetic (overall, thresholds, vetoes, verdict, quorum) is redone
by ``council_v2.scoring``.  A second column applies the Council v2 evidence
cap using the alumni repositories as published (``main``) today.

The Registry section at the end is produced the only way Council v2 allows:
each legacy JSON is wrapped in a legacy-import record, signed (ephemeral key,
in a temporary directory), verified, and rendered by ``council_v2.registry``.

Usage::

    python -m council_v2.recompute [--repos-root ..] [--ref main] [--out council_v2/recomputed_2026-09-30.md]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any

FACULTY = Path(__file__).resolve().parents[1]
if str(FACULTY) not in sys.path:
    sys.path.insert(0, str(FACULTY))

from council_v2 import CRITERIA_ORDER, registry, scoring  # noqa: E402
from council_v2.evidence import scan_repo  # noqa: E402
from council_v2.legacy import LEGACY_SEATS, identical_vectors, legacy_records  # noqa: E402
from council_v2.record import write_signed  # noqa: E402
from council_v2.signing import Ed25519Signer  # noqa: E402

SHORT = {"anthropic_chair": "Anthropic", "cerebras_reasoning": "Cerebras", "moonshot_longctx": "Moonshot", "groq_velocity": "Groq"}


def _git(root: Path, *args: str) -> str:
    cp = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return cp.stdout.strip() if cp.returncode == 0 else ""


def superseded_versions(rel: str) -> list[dict[str, Any]]:
    """Earlier committed versions of a review file whose scores differ from the current one."""
    shas = _git(FACULTY, "log", "--format=%H", "--", rel).splitlines()
    out = []
    current = None
    for i, sha in enumerate(shas):
        raw = _git(FACULTY, "show", f"{sha}:{rel}")
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue
        vec = [d["criterion_scores"][k]["score"] for k in CRITERIA_ORDER]
        if i == 0:
            current = vec
            continue
        if vec != current:
            sc = scoring.score_seat(d["criterion_scores"])
            out.append({"commit": sha[:7], "scores": vec, "overall_recorded": d.get("overall_score"),
                        "overall_recomputed": sc.overall, "verdict_recorded": d.get("verdict"), "verdict_rule_based": sc.verdict,
                        "review_date": d.get("review_date")})
    return out


def fmt(x) -> str:
    return "—" if x is None else (f"{x:.2f}" if isinstance(x, float) else str(x))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repos-root", type=Path, default=FACULTY.parent)
    ap.add_argument("--ref", default="main", help="ref of the alumni repos for the evidence-cap column")
    ap.add_argument("--out", type=Path, default=FACULTY / "council_v2" / "recomputed_2026-09-30.md")
    args = ap.parse_args(argv)

    alumni_doc = json.loads((FACULTY / "alumni" / "alumni.json").read_text(encoding="utf-8"))
    alumni = {a["slug"]: a for a in alumni_doc["alumni"]}
    cands = {s: {"name": a["name"]["canonical"] or s, "specialty": a["specialty"]["poetic_name"], "number": a["number"],
                 "cohort": a["cohort"]} for s, a in alumni.items()}
    council = registry.load_council(FACULTY / "council" / "council.json")
    lmap = {s["legacy_seat_id"]: s["seat_id"] for s in council["seats"] if s.get("legacy_seat_id")}
    recs = legacy_records(FACULTY, "cohort-phase-0", candidates=cands, v2_seat_map=lmap) + \
        legacy_records(FACULTY, "cohort-q2-2026", candidates=cands, v2_seat_map=lmap)
    by_slug: dict[str, list[dict[str, Any]]] = {}
    for r in recs:
        by_slug.setdefault(r["candidate"]["slug"], []).append(r)
    order = sorted(by_slug, key=lambda s: cands.get(s, {}).get("number") or 99)
    commit = _git(FACULTY, "rev-parse", "--short", "HEAD")

    # ---------------- per-seat table and statistics ----------------
    filed = [r for r in recs if r["status"] == "ok"]
    deltas = [abs(r["recorded"]["overall_score"] - r["scoring"]["overall"]) for r in filed]
    nonzero = [d for d in deltas if d >= 0.01]
    verdict_diff = [r for r in filed if r["recorded"]["verdict"] != r["scoring"]["verdict"]]
    closer_mean = sum(1 for r in filed if abs(r["recorded"]["overall_score"] - r["scoring"]["arithmetic_mean"]) < abs(r["recorded"]["overall_score"] - r["scoring"]["overall"]))
    closer_weighted = sum(1 for r in filed if abs(r["recorded"]["overall_score"] - r["scoring"]["overall"]) < abs(r["recorded"]["overall_score"] - r["scoring"]["arithmetic_mean"]))
    null_recs = [r for r in recs if r["status"] == "null"]
    L: list[str] = []
    L += [
        "# Council 2026 — recomputation with the deterministic rubric",
        "",
        f"*Generated by `python -m council_v2.recompute` on faculty commit `{commit}`, 2026-09-30. "
        "Analysis, not a new defense: the seven scores are the 2026 model outputs on prose, unchanged; "
        "only the arithmetic is redone by `council_v2/scoring.py`.*",
        "",
        "## Key numbers",
        "",
        f"- **{len(filed)} JSON files** re-scored ({sum(1 for r in filed if 'phase-0' in r['session']['cohort'])} Phase 0, "
        f"{sum(1 for r in filed if 'q2' in r['session']['cohort'])} Q2), plus **{len(null_recs)} seats that wrote no file** "
        "(now explicit null records).",
        f"- The model-written overall differs from the rubric's weighted overall in **{len(nonzero)}/{len(filed)}** files "
        f"(mean |Δ| {sum(deltas) / len(deltas):.3f}, max |Δ| {max(deltas):.2f}). "
        f"The recorded value is closer to the unweighted mean in {closer_mean} files and to the weighted overall in {closer_weighted}.",
        f"- The recorded verdict differs from the rule-based verdict in **{len(verdict_diff)}** file{'s' if len(verdict_diff) != 1 else ''}: "
        + "; ".join(f"{cands[r['candidate']['slug']]['name']} / {SHORT[r['seat']['legacy_seat_id']]}: "
                    f"{r['recorded']['verdict']} → {r['scoring']['verdict']}" for r in verdict_diff) + ".",
    ]

    # council-level outcomes
    rule = scoring.QuorumRule(voting_seats=LEGACY_SEATS)
    outcomes_plain, outcomes_capped, repo_facts = {}, {}, {}
    for slug in order:
        o_plain, o_cap = [], []
        man = scan_repo(args.repos_root / slug, ref=args.ref)
        caps = scoring.evidence_caps(man)
        repo_facts[slug] = man
        for r in by_slug[slug]:
            sid = r["seat"]["legacy_seat_id"]
            if r["status"] != "ok":
                o_plain.append(scoring.SeatOutcome(sid, "missing"))
                o_cap.append(scoring.SeatOutcome(sid, "missing"))
                continue
            o_plain.append(scoring.SeatOutcome(sid, "ok", scoring.score_seat(r["scores_raw"])))
            o_cap.append(scoring.SeatOutcome(sid, "ok", scoring.score_seat(r["scores_raw"], caps)))
        outcomes_plain[slug] = scoring.decide_council(o_plain, rule)
        outcomes_capped[slug] = scoring.decide_council(o_cap, rule)
    n_pass = sum(1 for d in outcomes_plain.values() if d.outcome == scoring.OUTCOME_PASS)
    n_cap_veto = sum(1 for d in outcomes_capped.values() if d.outcome == scoring.OUTCOME_VETO)
    zero_art = sum(1 for m in repo_facts.values() if m.get("artifact_count", 0) == 0)
    L += [
        f"- Council outcome with the rules applied to the recorded scores: **{n_pass}/14 PASS**; "
        + ", ".join(f"{cands[s]['name']} {d.outcome}" for s, d in outcomes_plain.items() if d.outcome != scoring.OUTCOME_PASS)
        + "." + (" Sofia Lume's Anthropic veto (body_of_work_depth 4 < 5) is enforced: VETO, not certified."
                 if outcomes_plain.get("sofia-lume") and outcomes_plain["sofia-lume"].outcome == scoring.OUTCOME_VETO else ""),
        f"- With the Council v2 evidence cap (zero artifacts ⇒ body_of_work_depth ≤ 3 ⇒ veto), using the alumni repositories at `{args.ref}`: "
        f"**{zero_art}/14 repositories have zero artifacts**, so **{n_cap_veto}/14 outcomes become VETO**.",
        "- Reduced quorum: Ezio Cardone (no Cerebras file), Adèle Maurique and Tomaso Riviera (no Anthropic file). "
        "Their tally is **3/3**, not 4/4.",
    ]
    ident = identical_vectors(recs, 3)
    L.append("- Non-discriminating seats (same 7-score vector to ≥3 candidates): " + "; ".join(
        f"{SHORT[g['seat']]} gave {'·'.join(map(str, g['vector']))} to {len(g['candidates'])} "
        f"({', '.join(cands[c]['name'] for c in g['candidates'])})" for g in ident) + ".")

    sup = {}
    for r in filed:
        s = superseded_versions(r["source_file"])
        if s:
            sup[r["source_file"]] = s
    if sup:
        L.append("- Superseded reviews that survive only in git history: " + "; ".join(
            f"`{Path(f).name}` @ {v['commit']}: {'·'.join(map(str, v['scores']))}, model wrote {v['overall_recorded']} {v['verdict_recorded']}, "
            f"rubric gives {v['overall_recomputed']} {v['verdict_rule_based']}" for f, vs in sup.items() for v in vs) + ".")
    L.append("")

    # Registry claims
    L += ["## What the Registry claims vs. what the JSONs contain", "",
          "| Alumnus | Registry claim (site, `main`) | Registry README (`main`) | JSON files | Recorded overalls in the JSONs (A / C / M / G) |",
          "|---|---|---|---|---|"]
    for slug in order:
        a = alumni[slug]
        if a["cohort"] != "q2-2026":
            continue
        seats = {s["seat"]: s for s in a["council"]["seats"]}
        rec_line = " / ".join(fmt(seats[s]["overall_recorded"]) for s in LEGACY_SEATS)
        L.append(f"| {cands[slug]['name']} | {a['council']['claims']['site_registry']} | {a['council']['claims']['registry_readme']} | "
                 f"{a['council']['quorum']['seats_with_file']} | {rec_line} |")
    L += ["", "Scores shown on the site Registry for Ezio Cardone (9.3, 9.1, 8.9) and Adèle Maurique (9.4, 9.2, 8.9) exist in no JSON; "
          "the recorded values are 9.1 / 8.1 / 8.7 and 9.3 / 8.43 / 8.7.", ""]

    # per-alumnus table
    L += ["## Per alumnus", "",
          "| # | Alumnus | Cohort | JSONs | Rule-based outcome (recorded scores) | Tally | With v2 evidence cap | Repo artifacts (`" + args.ref + "`) |",
          "|---|---|---|---|---|---|---|---|"]
    for slug in order:
        d, dc = outcomes_plain[slug], outcomes_capped[slug]
        m = repo_facts[slug]
        L.append(f"| {cands[slug]['number']:02d} | {cands[slug]['name']} | {cands[slug]['cohort']} | "
                 f"{sum(1 for r in by_slug[slug] if r['status'] == 'ok')}/4 | {d.outcome}"
                 + (" (reduced quorum)" if d.reduced_quorum else "") + f" | {d.tally} | {dc.outcome} | "
                 f"{m.get('artifact_count', 0)} ({', '.join(f['path'] for f in m.get('files', []))}) |")
    L.append("")

    # per-seat table
    L += ["## Per seat", "",
          "Scores in rubric order: body of work · uniqueness · voice · faithful distillation · synthetic transparency · placement · continuity. "
          "Weights 1.5 · 1.5 · 1 · 1 · 1 · 1 · 0.5; overall = weighted sum / 7.5.", "",
          "| Alumnus | Seat | Model (self-reported) | Scores | Overall written by model | Overall by rubric | Δ | Unweighted mean | Verdict written | Verdict by rule | Vetoes / thresholds missed |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for slug in order:
        for r in sorted(by_slug[slug], key=lambda r: LEGACY_SEATS.index(r["seat"]["legacy_seat_id"])):
            seat = SHORT[r["seat"]["legacy_seat_id"]]
            if r["status"] != "ok":
                L.append(f"| {cands[slug]['name']} | {seat} | — | *no file* | — | — | — | — | — | null | "
                         f"{(r['error'] or {}).get('claimed_cause') or 'seat failure not recorded'} |")
                continue
            sc = r["scoring"]
            delta = r["recorded"]["overall_score"] - sc["overall"]
            miss = "; ".join(sc["vetoes"]) or ", ".join(f"{k} < {scoring.BY_KEY[k].threshold}" for k in sc["below_threshold"]) or "—"
            mark = "**" if r["recorded"]["verdict"] != sc["verdict"] else ""
            L.append(f"| {cands[slug]['name']} | {seat} | `{r['model_self_reported']}` | {'·'.join(str(r['scores_raw'][k]) for k in CRITERIA_ORDER)} | "
                     f"{r['recorded']['overall_score']} | {sc['overall']:.2f} | {delta:+.2f} | {sc['arithmetic_mean']:.2f} | "
                     f"{r['recorded']['verdict']} | {mark}{sc['verdict']}{mark} | {miss} |")
    L.append("")

    # registry generated from signed records
    signer = Ed25519Signer.generate(label="ephemeral-recompute")
    with tempfile.TemporaryDirectory() as td:
        for r in recs:
            write_signed(r, Path(td) / r["session"]["session_id"] / f"{r['candidate']['slug']}__{r['seat']['legacy_seat_id']}.json", signer)
        rows, rejected = registry.build([td], signer.public_key, council)
        reg_md = registry.to_markdown(rows, council, rejected)
    L += ["## Registry generated from signed records only", "",
          "Each legacy JSON was wrapped in a `legacy-import` record, signed with an ephemeral Ed25519 key, verified and rendered by "
          "`council_v2.registry` (the same code as `scripts/build_registry.py`). A missing seat appears as `null`, never as a number.", "",
          reg_md.replace("<!-- GENERATED by scripts/build_registry.py from signed records only. Do not edit by hand. -->\n\n", ""), ""]

    L += ["## Rules applied and interpretations", "",
          "Per seat (admission/RUBRIC.md): weighted overall; thresholds ≥7 · ≥7 · ≥7 · ≥7 · ≥9 · ≥6 · ≥6; "
          "vetoes: synthetic transparency < 9, body of work < 5, specialty uniqueness < 5. "
          "Council (admission/COUNCIL_REVIEW.md): quorum 3 of 4; most restrictive seat wins.", ""]
    L += [f"- **{k}** {v}" for k, v in scoring.INTERPRETATIONS.items()]
    L += ["", "## Limits", "",
          "- The seven scores are what the 2026 models wrote after reading Dean-authored prose (and, in the Q2 run, for Groq, a bundle without the rubric); "
          "re-doing the arithmetic does not make them evidence.",
          "- The evidence-cap column applies today's repository state to May's reviews. It shows what Council v2 would decide on the same "
          "scores, not what the 2026 Council should have decided.",
          "- Model names are self-reported in the JSONs; no API response was stored, so they cannot be verified.", ""]
    args.out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
