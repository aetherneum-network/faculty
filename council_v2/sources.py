"""Read-only parsers for every public surface that describes an alumnus.

Used by ``scripts/build_alumni_json.py`` (to seed alumni/alumni.json with the
values actually found, contradictions included) and by
``scripts/check_consistency.py`` (to compare the surfaces against it).

Surfaces (paths relative to the directory that contains the ``faculty``
clone, i.e. the ``repos/`` folder with one clone per repository):

* ``<slug>/README.md``                                                alumnus repository README
* ``aetherneum-sites/university-aetherneum-com/alumni/<slug>.html``     site profile page
* ``aetherneum-sites/university-aetherneum-com/assets/diplomas/diploma-<slug>.svg``
* ``aetherneum-sites/aetherneum-com/registry.html``                     site Registry table
* ``registry/README.md``                                              registry repository table
* ``<faculty>/alumni/_ROSTER.md``, ``alumni/pending/<slug>.md``, ``cohort-q2-2026/intake/<slug>.md``

Nothing here writes files or touches the network.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

SLUGS = (
    "marco-aurelius", "lucia-solari", "riku-aetherian", "adrian-volta", "davide-ferri",
    "elena-tessera", "yara-indrani", "sofia-lume", "noa-cifratti", "tariq-al-khwarizmi",
    "costanza-notari", "ezio-cardone", "adele-maurique", "tomaso-riviera",
)
PHASE0 = SLUGS[:10]
Q2 = SLUGS[10:]

SITE_DIR = Path("aetherneum-sites/university-aetherneum-com")
SITE_REGISTRY = Path("aetherneum-sites/aetherneum-com/registry.html")
REGISTRY_README = Path("registry/README.md")

PRONOUNS = {
    "he": re.compile(r"\b(he|him|his|himself)\b", re.I),
    "she": re.compile(r"\b(she|her|hers|herself)\b", re.I),
}


def read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError):
        return None


def clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = html.unescape(s)
    s = re.sub(r"[*`]", "", s)
    s = s.replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s).strip().strip('"').strip()
    return s or None


def norm_key(s: str | None) -> str:
    """Comparison key: case-, punctuation- and whitespace-insensitive."""
    if not s:
        return ""
    s = clean(s) or ""
    s = s.lower().replace("æ", "ae")
    s = re.sub(r"[^a-z0-9.+ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def advisor_key(s: str | None) -> str:
    """'Claude Sonnet 4.6', 'Sonnet 4.6' and 'Faculty advisor: Sonnet 4.6' compare equal;
    '+ security-review skill' or '(1M context)' are kept as a suffix."""
    if not s:
        return ""
    m = re.search(r"(sonnet|opus|haiku|fable|mythos)\s*([0-9]+(?:\.[0-9]+)?)", s, re.I)
    if not m:
        return norm_key(s)
    base = f"claude {m.group(1).lower()} {m.group(2)}"
    rest = norm_key(s[m.end():])
    return f"{base} {rest}".strip()


def text_key(s: str | None) -> str:
    """Comparison key for prose (theses): ignores case, punctuation and a
    trailing ellipsis, so 'A: b.' and 'a b' compare equal."""
    if not s:
        return ""
    s = (clean(s) or "").lower().replace("æ", "ae").rstrip("…").rstrip(".")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def is_truncated(s: str | None) -> bool:
    return bool(s) and (s.rstrip().endswith("…") or s.rstrip().endswith("..."))


def pronoun_counts(text: str | None) -> dict[str, int]:
    if not text:
        return {}
    return {k: len(rx.findall(text)) for k, rx in PRONOUNS.items()}


def _section(md: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\s*$(.*?)(?=^## |\Z)", md, re.M | re.S)
    return m.group(1) if m else ""


# --------------------------------------------------------------------------
# Markdown profile (alumnus README and alumni/pending/<slug>.md share the format)
# --------------------------------------------------------------------------


def parse_profile_md(md: str | None) -> dict[str, Any]:
    if not md:
        return {}
    out: dict[str, Any] = {}
    m = re.search(r"^# (.+)$", md, re.M)
    out["name"] = clean(m.group(1)) if m else None
    m = re.search(r"^\*\*(.+?) · Aetherneum University · Class of '26 · (Synthetic alumn\w+)\*\*", md, re.M)
    if m:
        out["role"], out["synthetic_label"] = clean(m.group(1)), m.group(2)
    m = re.search(r"^>\s*\*(.+?)\*\s*$", md, re.M)
    out["motto"] = clean(m.group(1)) if m else None
    for label, key in (("Email", "email"), ("Master Degree", "degree"), ("Faculty Advisor", "advisor"),
                       ("Primary Placement", "placement")):
        m = re.search(rf"^\|[^|\n]*?{label}\s*\|\s*(.*?)\s*\|\s*$", md, re.M)
        out[key] = clean(m.group(1)) if m else None
    if out.get("degree"):
        out["specialty"] = clean(re.sub(r"^Master of the Æther\s*[—-]\s*", "", out["degree"]))
    thesis = _section(md, "Master Thesis")
    m = re.search(r'^>\s*\*"(.+?)"\*', thesis, re.M | re.S)
    out["thesis"] = clean(m.group(1)) if m else None
    m = re.search(r"advised by ([^,.\n]+(?:\.[0-9]+)?(?: \([^)]*\))?)", thesis)
    out["advisor_thesis_section"] = clean(m.group(1)) if m else None
    out["cum_laude"] = "cum laude" in thesis.lower()
    dip = _section(md, "Diploma")
    m = re.search(r"defended the thesis titled\s*\n(.*?)\n\s*before the Faculty Board", dip, re.S)
    out["diploma_thesis"] = clean(" ".join(ln.strip() for ln in m.group(1).splitlines())) if m else None
    m = re.search(r"Faculty advisor:\s*(.+)$", dip, re.M)
    out["diploma_advisor"] = clean(m.group(1)) if m else None
    m = re.search(r"MASTER OF THE ÆTHER · (.+)$", dip, re.M)
    out["diploma_specialty"] = clean(m.group(1)) if m else None
    body = re.sub(r"```.*?```", "", md, flags=re.S)
    body = re.split(r"^## About Aetherneum University", body, flags=re.M)[0]
    out["pronouns"] = pronoun_counts(body)
    out["mentions_the_platform"] = len(re.findall(r"\bthe platform\b", body, re.I))
    return out


# --------------------------------------------------------------------------
# Site profile page (HTML)
# --------------------------------------------------------------------------


def _html_lines(page: str) -> list[str]:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = re.sub(r"<(br|p|div|h\d|li|tr|section|dt|dd|span class=\"label\")[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    return [ln.strip() for ln in t.splitlines() if ln.strip()]


def _after(lines: list[str], label: str) -> str | None:
    for i, ln in enumerate(lines):
        if ln == label and i + 1 < len(lines):
            return clean(lines[i + 1])
    return None


def parse_site_page(page: str | None) -> dict[str, Any]:
    if not page:
        return {}
    lines = _html_lines(page)
    out: dict[str, Any] = {}
    m = re.search(r"<title>(.*?) — (.*?) · Aetherneum University</title>", page)
    if m:
        out["name"], out["role"] = clean(m.group(1)), clean(m.group(2))
    for label, key in (("Master Degree", "degree"), ("Faculty Advisor", "advisor"), ("Primary Placement", "placement"),
                       ("Master Thesis", "thesis")):
        out[key] = _after(lines, label)
    if out.get("degree"):
        out["specialty"] = clean(re.sub(r"^Master of the Æther\s*[—-]\s*", "", out["degree"]))
    for ln in lines:
        m = re.search(r"advised by ([^,.\n]+(?:\.[0-9]+)?)", ln)
        if m and "Defended" in ln:
            out["advisor_thesis_section"] = clean(m.group(1))
            out["cum_laude"] = "cum laude" in ln.lower()
            break
    for ln in lines:
        m = re.search(r"Faculty advisor:\s*(.+)$", ln)
        if m:
            out["diploma_advisor"] = clean(m.group(1))
            break
    bio = _after(lines, "Biography")
    out["pronouns"] = pronoun_counts(" ".join(lines[lines.index("Biography"):lines.index("Biography") + 12]) if "Biography" in lines else bio)
    out["jsonld_person"] = bool(re.search(r'"@type"\s*:\s*"Person"', page))
    out["mentions_the_platform"] = sum(len(re.findall(r"\bthe platform\b", ln, re.I)) for ln in lines)
    m = re.search(r'src="/assets/diplomas/(diploma-[a-z-]+\.svg)"', page)
    out["diploma_svg_ref"] = m.group(1) if m else None
    return out


# --------------------------------------------------------------------------
# Diploma SVG
# --------------------------------------------------------------------------


def parse_diploma_svg(svg: str | None) -> dict[str, Any]:
    if not svg:
        return {}
    out: dict[str, Any] = {}
    for marker, key in (("ALUMNUS_NAME", "name"), ("SPECIALTY", "specialty"), ("THESIS_TITLE", "thesis")):
        m = re.search(rf"<!--\s*{marker}\s*-->(.*?)</text>", svg, re.S)
        out[key] = clean(m.group(1)) if m else None
    if out.get("specialty"):
        out["specialty"] = clean(re.sub(r"^in\s+", "", out["specialty"]))
    m = re.search(r"FACULTY ADVISOR:\s*(.*?)\s*(?:&#xB7;|·)", svg)
    out["advisor"] = clean(m.group(1)) if m else None
    return out


# --------------------------------------------------------------------------
# Roster, registries, intake
# --------------------------------------------------------------------------


def parse_roster(md: str | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not md:
        return out
    for m in re.finditer(r"^\| (\d\d) \| \*\*(.+?)\*\* \| (.+?) \| (.+?) \| (.+?) \| (\w+) \| \[([a-z-]+)\]", md, re.M):
        out[m.group(7)] = {
            "number": int(m.group(1)), "name": clean(m.group(2)), "specialty": clean(m.group(3)),
            "advisor": clean(m.group(4)), "placement": clean(m.group(5)), "status": m.group(6),
        }
    return out


def parse_site_registry(page: str | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not page:
        return out
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 5:
            continue
        m = re.search(r"/alumni/([a-z-]+)\.html", cells[1])
        if not m:
            continue
        council = clean(re.sub(r"<[^>]+>", " ", cells[4]))
        paren = re.search(r"\(([^)]*)\)", council or "")
        scores = [x.strip() for x in paren.group(1).split("/")] if paren else []
        if not all(re.fullmatch(r"\d+(?:\.\d+)?|—|-", x) for x in scores):
            scores = []  # a parenthetical note, not a score line
        tally = re.match(r"(\d)/(\d)", council or "")
        out[m.group(1)] = {
            "number": int(clean(cells[0]) or 0),
            "specialty": clean(re.sub(r"<[^>]+>", " ", cells[2])),
            "cohort": clean(re.sub(r"<[^>]+>", " ", cells[3])),
            "council": council,
            "claimed_tally": tally.group(0) if tally else None,
            "claimed_scores": scores,  # order on the page: Anthropic / Cerebras / Moonshot / Groq
        }
    return out


def parse_registry_readme(md: str | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not md:
        return out
    for m in re.finditer(r"^\| (\d\d) \| (.+?) \| (.+?) \| (.+?) \| \[([a-z-]+)\]", md, re.M):
        tally = re.search(r"(\d)/(\d)", m.group(4))
        out[m.group(5)] = {"number": int(m.group(1)), "name": clean(m.group(2)), "specialty": clean(m.group(3)),
                           "defense": clean(m.group(4)), "claimed_tally": tally.group(0) if tally else None}
    return out


def parse_intake(md: str | None) -> dict[str, Any]:
    if not md:
        return {}
    out = {}
    for label, key in (("Proposed specialty", "specialty"), ("Proposed Faculty Advisor", "advisor"),
                       ("Date of intake", "date"), ("Working name", "name")):
        m = re.search(rf"^\| {label} \| (.+?) \|\s*$", md, re.M)
        out[key] = clean(m.group(1)) if m else None
    if out.get("specialty"):
        out["specialty"] = clean(re.sub(r"^Master of the Æther\s*[—-]\s*", "", out["specialty"]))
    return out


# --------------------------------------------------------------------------
# One call: every surface for one alumnus
# --------------------------------------------------------------------------


def read_sibling(repos_root: Path, rel: Path | str, ref: str | None = None) -> str | None:
    """Read ``<repos_root>/<repo>/<path>`` from the working tree, or from commit
    ``ref`` of that repository (``git show ref:path``, read-only)."""
    rel = Path(rel)
    if not ref:
        return read(repos_root / rel)
    from .evidence import read_bytes

    repo, inner = rel.parts[0], Path(*rel.parts[1:]).as_posix()
    data = read_bytes(repos_root / repo, inner, ref)
    return None if data is None else data.decode("utf-8", "replace").replace("\r\n", "\n")


def collect(slug: str, *, repos_root: Path, faculty_root: Path, ref: str | None = None) -> dict[str, dict[str, Any]]:
    """Return ``{surface_name: parsed_fields}``.  Missing files give ``{}``.

    ``ref`` (e.g. ``"main"``) reads the sibling repositories at that commit;
    faculty files are always read from ``faculty_root``'s working tree.
    """
    s: dict[str, dict[str, Any]] = {}
    s["alumnus_readme"] = parse_profile_md(read_sibling(repos_root, Path(slug) / "README.md", ref))
    s["site_profile"] = parse_site_page(read_sibling(repos_root, SITE_DIR / "alumni" / f"{slug}.html", ref))
    s["diploma_svg"] = parse_diploma_svg(read_sibling(repos_root, SITE_DIR / "assets" / "diplomas" / f"diploma-{slug}.svg", ref))
    s["roster"] = parse_roster(read(faculty_root / "alumni" / "_ROSTER.md")).get(slug, {})
    s["site_registry"] = parse_site_registry(read_sibling(repos_root, SITE_REGISTRY, ref)).get(slug, {})
    s["registry_readme"] = parse_registry_readme(read_sibling(repos_root, REGISTRY_README, ref)).get(slug, {})
    pending = faculty_root / "alumni" / "pending" / f"{slug}.md"
    if pending.exists():
        s["pending_profile"] = parse_profile_md(read(pending))
    intake = faculty_root / "cohort-q2-2026" / "intake" / f"{slug}.md"
    if intake.exists():
        s["intake"] = parse_intake(read(intake))
    return s


# Field → [(surface, key)] used for comparisons.  "where" strings are built as
# "<surface>:<key>" with the path given in SURFACE_PATHS.
FIELD_SOURCES: dict[str, list[tuple[str, str]]] = {
    "name": [("alumnus_readme", "name"), ("site_profile", "name"), ("diploma_svg", "name"), ("roster", "name"),
             ("registry_readme", "name"), ("pending_profile", "name"), ("intake", "name")],
    "role": [("alumnus_readme", "role"), ("site_profile", "role"), ("pending_profile", "role")],
    "specialty": [("alumnus_readme", "specialty"), ("alumnus_readme", "diploma_specialty"), ("site_profile", "specialty"),
                  ("diploma_svg", "specialty"), ("roster", "specialty"), ("site_registry", "specialty"),
                  ("registry_readme", "specialty"), ("pending_profile", "specialty"), ("intake", "specialty")],
    "faculty_advisor": [("alumnus_readme", "advisor"), ("alumnus_readme", "advisor_thesis_section"),
                        ("alumnus_readme", "diploma_advisor"), ("site_profile", "advisor"),
                        ("site_profile", "advisor_thesis_section"), ("site_profile", "diploma_advisor"),
                        ("diploma_svg", "advisor"), ("roster", "advisor"), ("pending_profile", "advisor"),
                        ("intake", "advisor")],
    "placement": [("alumnus_readme", "placement"), ("site_profile", "placement"), ("roster", "placement"),
                  ("pending_profile", "placement")],
    "thesis": [("alumnus_readme", "thesis"), ("alumnus_readme", "diploma_thesis"), ("site_profile", "thesis"),
               ("diploma_svg", "thesis"), ("pending_profile", "thesis")],
}


def surface_path(surface: str, slug: str) -> str:
    return {
        "alumnus_readme": f"{slug}/README.md",
        "site_profile": f"aetherneum-sites/university-aetherneum-com/alumni/{slug}.html",
        "diploma_svg": f"aetherneum-sites/university-aetherneum-com/assets/diplomas/diploma-{slug}.svg",
        "roster": "faculty/alumni/_ROSTER.md",
        "site_registry": "aetherneum-sites/aetherneum-com/registry.html",
        "registry_readme": "registry/README.md",
        "pending_profile": f"faculty/alumni/pending/{slug}.md",
        "intake": f"faculty/cohort-q2-2026/intake/{slug}.md",
    }[surface]


KEY_LABEL = {
    "advisor": "metadata table 'Faculty Advisor'",
    "advisor_thesis_section": "Master Thesis paragraph 'advised by'",
    "diploma_advisor": "diploma footer 'Faculty advisor'",
    "diploma_thesis": "diploma block thesis",
    "diploma_specialty": "diploma block specialty",
    "thesis": "Master Thesis",
    "specialty": "Master Degree specialty",
    "placement": "Primary Placement",
    "name": "name",
    "role": "role line",
}
SURFACE_KEY_LABEL = {
    ("diploma_svg", "advisor"): "SVG footer 'FACULTY ADVISOR'",
    ("diploma_svg", "thesis"): "SVG THESIS_TITLE",
    ("diploma_svg", "specialty"): "SVG SPECIALTY",
    ("diploma_svg", "name"): "SVG ALUMNUS_NAME",
    ("roster", "advisor"): "roster column 'Faculty Advisor'",
    ("roster", "specialty"): "roster column 'Master of the Æther in'",
    ("roster", "placement"): "roster column 'Primary Placement'",
    ("roster", "name"): "roster column 'Alumnus'",
    ("intake", "advisor"): "intake 'Proposed Faculty Advisor'",
    ("intake", "specialty"): "intake 'Proposed specialty'",
    ("intake", "name"): "intake 'Working name'",
    ("site_registry", "specialty"): "Registry table column 'Master of the Æther in'",
    ("registry_readme", "specialty"): "Registry table column 'Master of the Æther in'",
    ("registry_readme", "name"): "Registry table column 'Agent'",
    ("site_profile", "name"): "<title>",
    ("site_profile", "role"): "<title>",
}


def where(surface: str, key: str, slug: str) -> str:
    label = SURFACE_KEY_LABEL.get((surface, key), KEY_LABEL.get(key, key))
    return f"{surface_path(surface, slug)} — {label}"


def values_for(field: str, surfaces: dict[str, dict[str, Any]], slug: str) -> list[tuple[str, str]]:
    """[(value, where)] for every surface that declares ``field``."""
    out = []
    for surface, key in FIELD_SOURCES[field]:
        v = (surfaces.get(surface) or {}).get(key)
        if v:
            out.append((v, where(surface, key, slug)))
    return out


def keyfn_for(field: str):
    return {"faculty_advisor": advisor_key, "thesis": text_key}.get(field, norm_key)


def canon_key(field: str, value: str) -> str:
    """Key used to decide whether a surface agrees with a canonical value.
    For advisors, parenthetical annotations ('(Dean, pilot Q2 cohort)') are ignored."""
    if field == "faculty_advisor":
        return advisor_key(re.sub(r"\([^)]*\)", "", value))
    return keyfn_for(field)(value)


def group_values(pairs: list[tuple[str, str]], keyfn=norm_key) -> list[dict[str, Any]]:
    """Group identical (normalised) values: [{value, where:[...]}] in first-seen order."""
    groups: dict[str, dict[str, Any]] = {}
    for value, w in pairs:
        k = keyfn(value)
        if k not in groups:
            groups[k] = {"value": value, "where": []}
        groups[k]["where"].append(w)
    return list(groups.values())


def distinct_keys(field: str, pairs: list[tuple[str, str]]) -> set[str]:
    """Distinct comparison keys, treating a truncated value ('…') that is a
    prefix of a longer one as the same value."""
    kf = keyfn_for(field)
    keys = {kf(v) for v, _ in pairs}
    trunc = {kf(v) for v, _ in pairs if is_truncated(v)}
    for t in trunc:
        if any(k != t and k.startswith(t) for k in keys):
            keys.discard(t)
    return keys
