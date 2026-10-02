"""Compare alumni/alumni.json with every public surface; list each divergence.

Divergence kinds:

* ``MISMATCH``   a canonical value is set and a surface shows something else
* ``UNRESOLVED`` no canonical value and the surfaces disagree among themselves
                 (a placement under name review is reported as ``UNRESOLVED (name review)``)
* ``STALE``      the values alumni.json recorded no longer match the surfaces
                 (regenerate with scripts/build_alumni_json.py, then re-curate)
* ``REGISTRY``   a Registry claims a tally or scores that the Council JSONs do not contain
* ``POLICY``     a surface contradicts a declared property (e.g. JSON-LD "@type": "Person"
                 for a synthetic alumnus; a veto-pending alumnus shown without the veto)
* ``MISSING``    an expected surface file does not exist

Read-only: it opens files and runs ``git show`` only when ``ref`` is given.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping

from . import sources as S

FIELDS = ("name", "role", "specialty", "faculty_advisor", "placement", "thesis")


@dataclass
class Divergence:
    kind: str
    slug: str
    field: str
    where: str
    found: Any
    expected: Any = None

    def line(self) -> str:
        exp = f" | expected: {self.expected!r}" if self.expected is not None else ""
        found = self.found if isinstance(self.found, str) else repr(self.found)
        return f"DIVERGENCE[{self.kind}] {self.slug} · {self.field} · {self.where} | found: {found}{exp}"


def _canonical(a: Mapping[str, Any], field: str) -> str | None:
    if field == "specialty":
        return a["specialty"].get("poetic_name")
    return (a.get(field) or {}).get("canonical")


def _recorded_pairs(a: Mapping[str, Any], field: str) -> set[tuple[str, str]]:
    if field == "thesis":
        items = [(v["text"], w) for v in a["thesis"]["variants"] for w in v["where"]]
    else:
        items = [(v["value"], w) for v in a[field]["declared_values_found"] for w in v["where"]]
    return {(S.keyfn_for(field)(v), w) for v, w in items}


def check_alumnus(a: Mapping[str, Any], surfaces: Mapping[str, Mapping[str, Any]]) -> list[Divergence]:
    slug = a["slug"]
    out: list[Divergence] = []
    for surf in ("alumnus_readme", "site_profile", "diploma_svg"):
        if not surfaces.get(surf):
            out.append(Divergence("MISSING", slug, surf, S.surface_path(surf, slug), "file not found or unparseable"))
    for field in FIELDS:
        pairs = S.values_for(field, surfaces, slug)
        canon = _canonical(a, field)
        if canon:
            ck = S.canon_key(field, canon)
            for v, w in pairs:
                if S.canon_key(field, v) != ck and not (S.is_truncated(v) and ck.startswith(S.canon_key(field, v))):
                    out.append(Divergence("MISMATCH", slug, field, w, v, canon))
        else:
            keys = S.distinct_keys(field, pairs)
            if len(keys) > 1:
                groups = S.group_values(pairs, S.keyfn_for(field))
                kind = "UNRESOLVED (name review)" if field == "placement" and a["placement"].get("name_review") else "UNRESOLVED"
                out.append(Divergence(kind, slug, field, f"{len(keys)} distinct values on {len(pairs)} surfaces",
                                      [g["value"] for g in groups]))
        now = {(S.keyfn_for(field)(v), w) for v, w in pairs}
        rec = _recorded_pairs(a, field)
        if now != rec:
            added = sorted(w for _, w in now - rec)
            removed = sorted(w for _, w in rec - now)
            out.append(Divergence("STALE", slug, field, "alumni.json vs surfaces",
                                  {"changed_or_new_on": added, "no_longer_on": removed}))
    # pronouns
    if not a.get("pronouns", {}).get("canonical"):
        counts = {k: surfaces.get(k, {}).get("pronouns") for k in ("alumnus_readme", "site_profile")}
        out.append(Divergence("UNRESOLVED", slug, "pronouns", "alumnus_readme vs site_profile", counts))
    # registries
    filed = [s for s in a["council"]["seats"] if s["status"] == "file"]
    for surf in ("site_registry", "registry_readme"):
        claim = (surfaces.get(surf) or {}).get("claimed_tally")
        if claim and int(claim.split("/")[1]) != len(filed):
            out.append(Divergence("REGISTRY", slug, "council tally", S.surface_path(surf, slug), claim,
                                  f"{sum(1 for s in filed if s['verdict_rule_based'] == 'PASS')}/{len(filed)} (JSON files: {len(filed)})"))
    shown = (surfaces.get("site_registry") or {}).get("claimed_scores") or []
    by_seat = {s["seat"]: s for s in a["council"]["seats"]}
    for sid, val in zip(("anthropic_chair", "cerebras_reasoning", "moonshot_longctx", "groq_velocity"), shown):
        seat = by_seat.get(sid, {})
        if val in ("—", "-"):
            if seat.get("status") == "file":
                out.append(Divergence("REGISTRY", slug, f"score {sid}", S.surface_path("site_registry", slug), val, seat.get("overall_recorded")))
            continue
        if seat.get("status") != "file":
            out.append(Divergence("REGISTRY", slug, f"score {sid}", S.surface_path("site_registry", slug), val, "no JSON for this seat"))
        elif abs(float(val) - float(seat["overall_recorded"])) >= 0.005:
            out.append(Divergence("REGISTRY", slug, f"score {sid}", S.surface_path("site_registry", slug), val,
                                  f"{seat['overall_recorded']} recorded, {seat['overall_recomputed']} recomputed"))
    # policy
    if (surfaces.get("site_profile") or {}).get("jsonld_person"):
        out.append(Divergence("POLICY", slug, "json-ld", S.surface_path("site_profile", slug), '"@type": "Person"',
                              "a non-Person type for a synthetic alumnus (review §5)"))
    if a["flags"].get("veto_pending"):
        for surf in ("site_registry", "registry_readme"):
            txt = str((surfaces.get(surf) or {}).get("council") or (surfaces.get(surf) or {}).get("defense") or "")
            if txt and "veto" not in txt.lower():
                out.append(Divergence("POLICY", slug, "veto_pending", S.surface_path(surf, slug), txt, "shown as veto pending"))
    return out


def check_all(alumni_doc: Mapping[str, Any], *, repos_root: Path, faculty_root: Path, ref: str | None = None,
              only: str | None = None) -> list[Divergence]:
    out: list[Divergence] = []
    for a in alumni_doc["alumni"]:
        if only and a["slug"] != only:
            continue
        surfaces = S.collect(a["slug"], repos_root=repos_root, faculty_root=faculty_root, ref=ref)
        out += check_alumnus(a, surfaces)
    return out


def summary(divs: list[Divergence]) -> dict[str, int]:
    c: dict[str, int] = {}
    for d in divs:
        c[d.kind] = c.get(d.kind, 0) + 1
    return dict(sorted(c.items()))


def to_json(divs: list[Divergence]) -> list[dict[str, Any]]:
    return [asdict(d) for d in divs]
