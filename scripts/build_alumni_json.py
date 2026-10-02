#!/usr/bin/env python3
"""Build alumni/alumni.json — one record per alumnus — from the current sources.

Reads (never writes) the sibling clones next to the faculty repository:
alumnus READMEs, site profile pages, diploma SVGs, the site Registry, the
registry README; and, inside faculty: _ROSTER.md, pending profiles, intakes
and the 2026 Council JSONs.

Contradictions are RECORDED, not resolved:

* ``declared_values_found`` / ``variants`` list every distinct value and
  where it was found;
* ``canonical`` is filled automatically only when every surface agrees; a
  value chosen by a human in an existing alumni.json is preserved on
  regeneration (``--reset`` discards human choices);
* placement descriptions that mention "the platform" or its trading
  domains are being reworded without client names: ``canonical`` stays null and
  ``name_review`` is true, whatever the surfaces say.

Personal e-mail addresses found in commit metadata are never written: only
alumnus identities (<first>.<last>@aetherneum.com) are kept; every other
identity, name and address, is collapsed into "[non-alumnus identity, redacted]".

Usage::

    python scripts/build_alumni_json.py [--repos-root ..] [--out alumni/alumni.json] [--reset]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

FACULTY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACULTY))

from council_v2 import CRITERIA_ORDER, scoring  # noqa: E402
from council_v2 import sources as S  # noqa: E402
from council_v2.bundle import blocking, lint_intake  # noqa: E402
from council_v2.evidence import NON_ALUMNUS, read_bytes, scan_repo  # noqa: E402
from council_v2.legacy import LEGACY_SEATS, LEGACY_PROVIDER, load_cohort, rescore  # noqa: E402

SCHEMA_VERSION = "aetherneum.alumni/1"
NAME_REVIEW_RX = re.compile(r"\bplatform\b|trading bot|trading domains|trading analytics", re.I)

# Proposed plain-language subtitles (review 2026-09-30 §5 "Nomi": keep the
# poetic name as a mark, always add a standard descriptive subtitle).  They
# are PROPOSALS: status stays "proposed" until the Faculty approves them.
SUBTITLES = {
    "marco-aurelius": "Frontend engineering — mobile UI and native-bridge crash resilience",
    "lucia-solari": "Backend engineering — idempotent services, locking and reversible migrations",
    "riku-aetherian": "Mobile release engineering — build triage, release freezes and gating",
    "adrian-volta": "Site reliability engineering — container infrastructure, routing and recovery",
    "davide-ferri": "Smart-contract engineering — EVM contracts and invariants",
    "elena-tessera": "Product design — design systems and brand visual identity",
    "yara-indrani": "Project management — asynchronous coordination of multi-agent work",
    "sofia-lume": "Quality engineering — pre-release test plans and release gating",
    "noa-cifratti": "Security engineering — zero-trust access review and audit preparation",
    "tariq-al-khwarizmi": "Data engineering — record unification and lossless re-seeding",
    "costanza-notari": "Procedural document classification — deadline-driven archives",
    "ezio-cardone": "Legal-entity dossier compilation — provenance-anchored corporate records",
    "adele-maurique": "Digital-signature forensics — point-in-time validation and chain of custody",
    "tomaso-riviera": "Probabilistic trading systems — signal validation and risk limits",
}

# docs/2026-09-30_Revisione_Aetherneum.html §4, table "I quattordici alumni".
REVIEW_2026_09_30 = {
    "marco-aurelius": (0, "tre tesi diverse; avatar sul sito diverso dal prompt"),
    "lucia-solari": (0, "le 3 revisioni chieste dal Chair non sono state fatte"),
    "riku-aetherian": (0, "tre relatori diversi su quattro superfici"),
    "adrian-volta": (1, "\"tre deploy in produzione\" senza link"),
    "davide-ferri": (0, "\"audit-resistant\" dice il contrario di ciò che intende"),
    "elena-tessera": (0, "la responsabile del brand ha un avatar senza segno sintetico"),
    "yara-indrani": (0, "il video la presenta con un'altra specialità"),
    "sofia-lume": (0, "certificata nonostante il veto"),
    "noa-cifratti": (0, "revisioni non fatte; pronomi incoerenti"),
    "tariq-al-khwarizmi": (0, "due email d'autore diverse"),
    "costanza-notari": (0, "nessuna prova pubblica della pipeline"),
    "ezio-cardone": (0, "punteggi del Registry assenti nei JSON"),
    "adele-maurique": (0, "manca il seggio Anthropic"),
    "tomaso-riviera": (0, "\"money has been moved\" senza alcuna prova"),
}

FLAG_NAMES = (
    "veto_pending",
    "revisions_required_not_done",
    "rule_based_verdict_differs_from_recorded",
    "overall_recorded_differs_from_rubric",
    "reduced_quorum",
    "strictest_seat_missing",
    "registry_tally_overstated",
    "registry_scores_not_in_json",
    "phase0_retroactive_review",
    "phase0_claims_defended_cum_laude",
    "council_reviewed_prose_not_artifacts",
    "zero_artifacts",
    "intake_contains_steering",
    "council_review_precedes_repo",
    "multiple_thesis_variants",
    "advisor_contradiction",
    "placement_contradiction",
    "placement_under_name_review",
    "role_contradiction",
    "pronoun_inconsistency",
    "multiple_commit_addresses",
    "no_commits_authored_as_alumnus",
    "personal_addresses_in_commit_history",
    "jsonld_type_person",
    "identical_score_vector_seat",
)


_canon_key = S.canon_key


def unanimous(field: str, pairs: list[tuple[str, str]]) -> str | None:
    keys = {_canon_key(field, v) for v, _ in pairs}
    if len(keys) != 1:
        return None
    counts: dict[str, int] = {}
    for v, _ in pairs:
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=lambda v: (counts[v], -len(v)))


def declared(field: str, surfaces, slug) -> list[dict[str, Any]]:
    return S.group_values(S.values_for(field, surfaces, slug), S.keyfn_for(field))


def thesis_variants(surfaces, slug) -> list[dict[str, Any]]:
    groups = S.group_values(S.values_for("thesis", surfaces, slug), S.text_key)
    keys = [S.text_key(g["value"]) for g in groups]
    out = []
    for g, k in zip(groups, keys):
        v = {"text": g["value"], "where": g["where"], "truncated": S.is_truncated(g["value"])}
        if v["truncated"]:
            full = [i for i, k2 in enumerate(keys) if k2 != k and k2.startswith(k)]
            v["truncation_of_variant"] = full[0] if full else None
        out.append(v)
    return out


def sha_bytes(b: bytes | None) -> str | None:
    return hashlib.sha256(b).hexdigest() if b is not None else None


def council_block(slug: str, cohort_dir: str, reviews: dict, site_reg: dict, repo_reg: dict, roster: dict) -> dict[str, Any]:
    seats = []
    outcomes = []
    for sid in LEGACY_SEATS:
        entry = reviews.get(sid)
        if entry is None:
            seats.append({"seat": sid, "provider": LEGACY_PROVIDER[sid], "status": "no_file", "file": None,
                          "model_recorded": None, "scores": None, "overall_recorded": None,
                          "overall_recomputed": None, "verdict_recorded": None, "verdict_rule_based": None})
            outcomes.append(scoring.SeatOutcome(sid, "missing"))
            continue
        path, rv = entry
        rs = rescore(rv)
        sc = rs["scoring"]
        seats.append({
            "seat": sid,
            "provider": rv.get("reviewer_provider"),
            "status": "file",
            "file": f"{cohort_dir}/council-reviews/{path.name}",
            "model_recorded": rv.get("reviewer_model"),
            "model_provenance": "self-reported in the JSON; no API response stored",
            "review_date_recorded": rv.get("review_date"),
            "scores": {k: rv["criterion_scores"][k]["score"] for k in CRITERIA_ORDER},
            "overall_recorded": rv.get("overall_score"),
            "overall_recomputed": sc.overall,
            "arithmetic_mean": sc.arithmetic_mean,
            "verdict_recorded": rv.get("verdict"),
            "verdict_rule_based": sc.verdict,
            "vetoes": sc.vetoes,
            "below_threshold": sc.below_threshold,
            "revisions_required": rv.get("revisions_required", []),
        })
        outcomes.append(scoring.SeatOutcome(sid, "ok", sc))
    rule = scoring.QuorumRule(voting_seats=LEGACY_SEATS)
    decision = scoring.decide_council(outcomes, rule)
    with_file = sum(1 for s in seats if s["status"] == "file")
    return {
        "cohort_dir": cohort_dir,
        "seats": seats,
        "quorum": {
            "seats_expected": len(LEGACY_SEATS),
            "seats_with_file": with_file,
            "min_required": rule.min_valid_seats,
            "met": with_file >= rule.min_valid_seats,
            "reduced": with_file < len(LEGACY_SEATS),
            "rule": "admission/COUNCIL_REVIEW.md: 'Minimum quorum: 3 reviews out of 4 available.' A seat without a file is absent, not a PASS.",
        },
        "rule_based_outcome": decision.outcome,
        "rule_based_tally": decision.tally,
        "rule_based_reasons": decision.reasons,
        "claims": {
            "roster_status": roster.get("status"),
            "site_registry": site_reg.get("council"),
            "site_registry_scores_order": "Anthropic / Cerebras / Moonshot / Groq",
            "site_registry_scores": site_reg.get("claimed_scores") or None,
            "registry_readme": repo_reg.get("defense"),
        },
    }


def build_one(slug: str, repos_root: Path, identical: dict[str, list[str]], ref: str | None = "main") -> dict[str, Any]:
    surfaces = S.collect(slug, repos_root=repos_root, faculty_root=FACULTY, ref=ref)
    roster = surfaces.get("roster", {})
    cohort_dir = "cohort-phase-0" if slug in S.PHASE0 else "cohort-q2-2026"
    reviews = load_cohort(FACULTY, cohort_dir).get(slug, {})
    council = council_block(slug, cohort_dir, reviews, surfaces.get("site_registry", {}), surfaces.get("registry_readme", {}), roster)
    ev = scan_repo(repos_root / slug, ref=ref)
    readme, site = surfaces.get("alumnus_readme", {}), surfaces.get("site_profile", {})

    name_pairs, role_pairs = S.values_for("name", surfaces, slug), S.values_for("role", surfaces, slug)
    spec_pairs, adv_pairs = S.values_for("specialty", surfaces, slug), S.values_for("faculty_advisor", surfaces, slug)
    plc_pairs = S.values_for("placement", surfaces, slug)
    named = any(NAME_REVIEW_RX.search(v) for v, _ in plc_pairs)
    theses = thesis_variants(surfaces, slug)
    distinct_theses = S.distinct_keys("thesis", S.values_for("thesis", surfaces, slug))

    pron = {k: surfaces[k].get("pronouns") for k in ("alumnus_readme", "site_profile", "pending_profile") if surfaces.get(k, {}).get("pronouns")}
    dominant = set()
    mixed = False
    for counts in pron.values():
        he, she = counts.get("he", 0), counts.get("she", 0)
        if he >= 2 and she >= 2:
            mixed = True
        if he or she:
            dominant.add("he/him" if he > she else "she/her")
    pron_ok = not mixed and len(dominant) == 1

    git = ev.get("git", {})
    idents = git.get("author_identities", {})
    alumnus_addrs = {re.search(r"<([^>]+)>", i).group(1) for i in idents if "@aetherneum.com" in i}
    name_canon = unanimous("name", name_pairs)
    authored_as = sum(n for i, n in idents.items() if name_canon and S.norm_key(i.split(" <")[0]) == S.norm_key(name_canon))
    redacted = sum(n for i, n in idents.items() if i == NON_ALUMNUS)
    site_avatar_sha = sha_bytes(read_bytes(repos_root / "aetherneum-sites", f"university-aetherneum-com/assets/alumni/{slug}.jpg", ref))
    repo_avatar_sha = sha_bytes(read_bytes(repos_root / slug, "avatar.jpg", ref))

    # ---- flags ------------------------------------------------------------
    seats = council["seats"]
    filed = [s for s in seats if s["status"] == "file"]
    flags: dict[str, bool] = {n: False for n in FLAG_NAMES}
    evidence: dict[str, str] = {}

    def flag(name: str, why: str) -> None:
        flags[name] = True
        evidence[name] = why

    vetoed = [s for s in filed if s["vetoes"] or (s["verdict_recorded"] == "FAIL")]
    if vetoed and roster.get("status") == "CONFERRED":
        flag("veto_pending", "; ".join(f"{s['seat']}: verdict_recorded={s['verdict_recorded']} vetoes={s['vetoes']}" for s in vetoed)
             + " — roster status CONFERRED (admission/RUBRIC.md: 'The veto cannot be overridden by the Dean.')")
    pwr = [s for s in filed if s["verdict_recorded"] == "PASS_WITH_REVISIONS" and s["revisions_required"]]
    if pwr and ev.get("artifact_count", 0) == 0:
        flag("revisions_required_not_done", f"{len(pwr[0]['revisions_required'])} revisions asked by {pwr[0]['seat']} "
             f"(e.g. {pwr[0]['revisions_required'][0][:90]!r}); repository {slug}@{(git.get('head_sha') or '')[:7]} has 0 artifacts")
    diff_v = [s for s in filed if s["verdict_recorded"] != s["verdict_rule_based"]]
    if diff_v:
        flag("rule_based_verdict_differs_from_recorded", "; ".join(f"{s['seat']}: {s['verdict_recorded']} -> {s['verdict_rule_based']}" for s in diff_v))
    diff_o = [s for s in filed if s["overall_recorded"] is not None and abs(s["overall_recorded"] - s["overall_recomputed"]) >= 0.01]
    if diff_o:
        flag("overall_recorded_differs_from_rubric", "; ".join(f"{s['seat']}: {s['overall_recorded']} vs {s['overall_recomputed']}" for s in diff_o))
    if council["quorum"]["reduced"]:
        flag("reduced_quorum", f"{council['quorum']['seats_with_file']}/4 seats wrote a JSON")
    if not reviews.get("anthropic_chair"):
        flag("strictest_seat_missing", "no anthropic_chair JSON (the seat the review calls 'lo scettico')")
    claims = [c for c in (surfaces.get("site_registry", {}).get("claimed_tally"), surfaces.get("registry_readme", {}).get("claimed_tally")) if c]
    over = [c for c in claims if int(c.split("/")[1]) > len(filed)]
    if over:
        flag("registry_tally_overstated", f"Registry shows {', '.join(sorted(set(over)))}; {len(filed)} JSON file(s) exist")
    claimed_scores = surfaces.get("site_registry", {}).get("claimed_scores") or []
    order = ("anthropic_chair", "cerebras_reasoning", "moonshot_longctx", "groq_velocity")
    bad = []
    for sid, shown in zip(order, claimed_scores):
        rec = reviews.get(sid)
        if shown in ("—", "-", ""):
            if rec is not None:
                bad.append(f"{sid}: shown '—' but a JSON exists")
            continue
        if rec is None:
            bad.append(f"{sid}: shown {shown} but no JSON exists")
        elif abs(float(shown) - float(rec[1].get("overall_score", -1))) >= 0.005:
            bad.append(f"{sid}: shown {shown}, JSON records {rec[1].get('overall_score')}")
    if bad:
        flag("registry_scores_not_in_json", "; ".join(bad))
    if slug in S.PHASE0:
        flag("phase0_retroactive_review", "Council JSONs dated 2026-05-14, after conferral (2026-05-10)")
        if readme.get("cum_laude") or site.get("cum_laude"):
            flag("phase0_claims_defended_cum_laude", "thesis section says 'Defended before the Faculty Board ... Awarded cum laude' (review §8: Phase 0 as 'profile-attested')")
    if ev.get("artifact_count", 0) == 0:
        flag("zero_artifacts", f"tracked files: {', '.join(f['path'] for f in ev.get('files', []))}")
        flag("council_reviewed_prose_not_artifacts", "the bundle contained intake/profile prose; the repository has no code, tests, CI, scenarios or releases")
    intake = FACULTY / "cohort-q2-2026" / "intake" / f"{slug}.md"
    if intake.exists():
        blk = blocking(lint_intake(intake))
        if blk:
            flag("intake_contains_steering", "; ".join(f"L{f.line}: {f.match!r}" for f in blk))
    dates = [s["review_date_recorded"] for s in filed if s.get("review_date_recorded")]
    first = git.get("first_commit_at")
    if dates and first:
        from datetime import datetime

        r0 = min(datetime.fromisoformat(d.replace("Z", "+00:00")) for d in dates)
        c0 = datetime.fromisoformat(first)
        if r0 < c0:
            flag("council_review_precedes_repo", f"earliest review {r0.isoformat()} < first repo commit {c0.isoformat()}")
    if len(distinct_theses) > 1:
        flag("multiple_thesis_variants", f"{len(distinct_theses)} distinct theses across surfaces")
    if len({_canon_key('faculty_advisor', v) for v, _ in adv_pairs}) > 1:
        flag("advisor_contradiction", " | ".join(sorted({v for v, _ in adv_pairs})))
    if len({S.norm_key(v) for v, _ in plc_pairs}) > 1:
        flag("placement_contradiction", f"{len({S.norm_key(v) for v, _ in plc_pairs})} distinct placement descriptions")
    if named:
        flag("placement_under_name_review", "a placement value mentions the platform or its trading domains; canonical left null")
    if len({S.norm_key(v) for v, _ in role_pairs}) > 1:
        flag("role_contradiction", " | ".join(sorted({v for v, _ in role_pairs})))
    if not pron_ok:
        flag("pronoun_inconsistency", json.dumps(pron))
    if len(alumnus_addrs) > 1:
        flag("multiple_commit_addresses", ", ".join(sorted(alumnus_addrs)))
    if authored_as == 0:
        flag("no_commits_authored_as_alumnus", "README says 'commits authored as <name>'; no commit has that author name")
    if redacted:
        flag("personal_addresses_in_commit_history", f"{redacted} commit(s) authored with non-alumnus addresses (redacted here; review §8)")
    if site.get("jsonld_person"):
        flag("jsonld_type_person", 'site profile JSON-LD declares "@type": "Person" (review §5)')
    if slug in identical:
        flag("identical_score_vector_seat", "; ".join(identical[slug]))

    rv = REVIEW_2026_09_30[slug]
    return {
        "number": roster.get("number"),
        "slug": slug,
        "name": {"canonical": name_canon, "declared_values_found": declared("name", surfaces, slug)},
        "role": {"canonical": unanimous("role", role_pairs), "declared_values_found": declared("role", surfaces, slug)},
        "specialty": {
            "poetic_name": unanimous("specialty", spec_pairs),
            "declared_values_found": declared("specialty", surfaces, slug),
            "descriptive_subtitle": {"text": SUBTITLES[slug], "status": "proposed", "esco_occupation": "[TO CONFIRM]"},
        },
        "cohort": "phase-0" if slug in S.PHASE0 else "q2-2026",
        "email": readme.get("email"),
        "synthetic_label": readme.get("synthetic_label"),
        "placement": {
            "canonical": None,
            "name_review": named,
            "note": "client names being removed — do not resolve" if named else "surfaces disagree; to be chosen by the Rector",
            "declared_values_found": declared("placement", surfaces, slug),
        },
        "faculty_advisor": {
            "canonical": unanimous("faculty_advisor", adv_pairs),
            "declared_values_found": declared("faculty_advisor", surfaces, slug),
        },
        "thesis": {"canonical": None, "variants": theses},
        "pronouns": {"canonical": next(iter(dominant)) if pron_ok else None, "counts_by_surface": pron},
        "council": council,
        "status": {
            "roster": roster.get("status"),
            "registry_site": surfaces.get("site_registry", {}).get("council"),
            "registry_readme": surfaces.get("registry_readme", {}).get("defense"),
            "recommended_until_redefense": (
                "veto pending" if flags["veto_pending"] else
                "profile-attested (not defended)" if slug in S.PHASE0 else
                "conferred on prose; re-defense with Council v2 required"
            ),
        },
        "flags": flags,
        "flag_evidence": evidence,
        "repo": {
            "name": slug,
            "head_sha": git.get("head_sha"),
            "files": [f["path"] for f in ev.get("files", [])],
            "artifact_count": ev.get("artifact_count", 0),
            "has_code": ev.get("has_code", False),
            "has_tests": ev.get("has_tests", False),
            "has_ci": ev.get("has_ci", False),
            "has_scenarios": ev.get("has_scenarios", False),
            "has_releases": ev.get("has_releases", False),
            "commit_count": git.get("commit_count"),
            "first_commit_at": git.get("first_commit_at"),
            "author_identities": idents,
            "commits_with_signature_header": git.get("commits_with_signature_header"),
        },
        "site": {
            "jsonld_type_person": site.get("jsonld_person"),
            "mentions_the_platform": {"alumnus_readme": readme.get("mentions_the_platform"), "site_profile": site.get("mentions_the_platform")},
            "avatar": {
                "repo_sha256": repo_avatar_sha,
                "site_sha256": site_avatar_sha,
                "same_file": repo_avatar_sha is not None and repo_avatar_sha == site_avatar_sha,
                "synthetic_marker_visible": None,
                "synthetic_marker_note": "requires human visual check (review §5: 'In tre casi manca ogni segno sintetico')",
            },
        },
        "external_review_2026_09_30": {"verifiability_0_to_3": rv[0], "main_issue": rv[1], "source": "docs/2026-09-30_Revisione_Aetherneum.html §4"},
    }


def merge_human_choices(new: dict[str, Any], old: dict[str, Any] | None) -> dict[str, Any]:
    """Keep canonical values and subtitle statuses a human set in the previous file."""
    if not old:
        return new
    for field in ("name", "role", "faculty_advisor", "thesis", "pronouns"):
        if old.get(field, {}).get("canonical") and old[field].get("canonical_set_by"):
            new[field]["canonical"] = old[field]["canonical"]
            new[field]["canonical_set_by"] = old[field]["canonical_set_by"]
    if not new["placement"]["name_review"] and old.get("placement", {}).get("canonical_set_by"):
        new["placement"]["canonical"] = old["placement"]["canonical"]
        new["placement"]["canonical_set_by"] = old["placement"]["canonical_set_by"]
    ost = (old.get("specialty") or {}).get("descriptive_subtitle") or {}
    if ost.get("status") and ost.get("status") != "proposed":
        new["specialty"]["descriptive_subtitle"] = ost
    return new


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repos-root", type=Path, default=FACULTY.parent)
    ap.add_argument("--out", type=Path, default=FACULTY / "alumni" / "alumni.json")
    ap.add_argument("--reset", action="store_true", help="discard canonical values chosen by humans")
    ap.add_argument("--ref", default="main", help="commit/branch of the sibling repos to read (default: main = published); '' = working trees")
    args = ap.parse_args(argv)

    from council_v2.legacy import identical_vectors, legacy_records

    recs = legacy_records(FACULTY, "cohort-phase-0") + legacy_records(FACULTY, "cohort-q2-2026")
    identical: dict[str, list[str]] = {}
    for grp in identical_vectors(recs, 3):
        for slug in grp["candidates"]:
            identical.setdefault(slug, []).append(
                f"{grp['seat']} gave {'·'.join(map(str, grp['vector']))} to {len(grp['candidates'])} candidates")

    old = {}
    if args.out.exists() and not args.reset:
        old = {a["slug"]: a for a in json.loads(args.out.read_text(encoding="utf-8")).get("alumni", [])}
    ref = args.ref or None
    alumni = [merge_human_choices(build_one(s, args.repos_root.resolve(), identical, ref), old.get(s)) for s in S.SLUGS]

    import subprocess

    from council_v2.bundle import git_head  # noqa: F401

    heads = {}
    for repo in ("aetherneum-sites", "registry", *S.SLUGS):
        p = args.repos_root / repo
        rv = subprocess.run(["git", "-C", str(p), "rev-parse", ref or "HEAD"], capture_output=True, text=True)
        br = subprocess.run(["git", "-C", str(p), "branch", "--show-current"], capture_output=True, text=True)
        heads[repo] = {"ref_read": ref or "working tree", "commit": rv.stdout.strip() if rv.returncode == 0 else None,
                       "checked_out_branch_at_generation": br.stdout.strip() if br.returncode == 0 else None}

    doc = {
        "$schema": "./alumni.schema.json",
        "schema_version": SCHEMA_VERSION,
        "generated_by": "scripts/build_alumni_json.py",
        "generated_at": "2026-09-30",
        "purpose": "Single source of truth for the 14 alumni. Profile, README, diploma SVG, Registry and Council bundle are to be generated from this file; scripts/check_consistency.py fails while any surface diverges.",
        "policy": {
            "contradictions": "recorded under declared_values_found / variants; never silently resolved",
            "canonical": "filled automatically only when every surface agrees (for the Faculty Advisor, 'Claude Sonnet 4.6' = 'Sonnet 4.6' and parenthetical notes such as '(Dean, pilot Q2 cohort)' are ignored; '+ <skill>' suffixes are not); otherwise null until a human sets it together with 'canonical_set_by'",
            "thesis": "canonical is null for every alumnus until the Rector chooses one thesis per alumnus (review §8, week 1)",
            "placement": "descriptions mentioning 'the platform' or its trading domains are being reworded without client names: canonical stays null",
            "privacy": "only alumnus identities (<first>.<last>@aetherneum.com) are recorded; every other commit identity, name and address, is redacted",
        },
        "sources": {
            "faculty_commit": git_head(FACULTY),
            "sibling_ref_read": ref or "working tree",
            "sibling_repos": heads,
        },
        "alumni": alumni,
    }
    args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_flags = sum(sum(a["flags"].values()) for a in alumni)
    print(f"wrote {args.out} — {len(alumni)} alumni, {n_flags} flags set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
