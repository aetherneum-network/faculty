"""One identical bundle for every seat, hashed; plus the intake lint.

Council v2 rule 5 (review 2026-09-30 §3): "Intake neutri. Nessuna frase sui
voti attesi. Lo stesso bundle, con lo stesso hash, va a tutti i seggi."

* ``build_bundle`` assembles charter, faculty board, rubric, roster, intake,
  profile, the repository evidence manifest and (optionally) the executor
  result into one deterministic text.  Every seat receives exactly this text;
  its SHA-256 is written into every seat record.  There is no per-seat
  "compact"/"mini" variant (the 2026-Q2 Groq seat got a bundle without the
  rubric).
* Text files are normalised to LF before hashing so that a Windows checkout
  (CRLF) and a Linux CI checkout produce the same hash; each part also records
  its git blob id, which identifies the committed content independently.
* ``lint_intake`` flags sentences that tell the Council what to score.  A
  ``block`` finding stops the run (``SteeringError``) — the Dean must rewrite
  the intake, the orchestrator never edits it.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable

from . import CRITERIA_ORDER

BUNDLE_FORMAT = "aetherneum.council-v2.bundle/1"

# Fixed bundle parts, in order.  Paths are relative to the faculty repo root.
STANDARD_PARTS = (
    ("charter", "charter/CHARTER.md"),
    ("faculty_board", "charter/FACULTY_BOARD.md"),
    ("rubric", "admission/RUBRIC.md"),
    ("roster", "alumni/_ROSTER.md"),
)

# --------------------------------------------------------------------------
# Intake lint
# --------------------------------------------------------------------------

_CRIT = "|".join(CRITERIA_ORDER)
_CRIT_HUMAN = (
    r"body[- ]of[- ]work(?: depth)?|specialty uniqueness|uniqueness|voice(?: & personality)?|"
    r"faithful distillation|synthetic transparency|placement fit|continuity"
)

STEERING_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    (
        "council-directive", "block",
        re.compile(
            r"\b(?:the\s+)?council\s+(?:should|must|will|would|ought\s+to|is\s+expected\s+to)\s+"
            r"(?:(?:be\s+able\s+to\s+)?(?:find|score|rate|see|conclude|agree|give|grade|read|judge|award))\b",
            re.I,
        ),
        "tells the Council what to find or how to score",
    ),
    (
        "score-expectation", "block",
        re.compile(
            r"\b(?:should|will|would|must|is\s+expected\s+to|is\s+likely\s+to)\s+"
            r"(?:score|rate|grade)\s+(?:very\s+)?(?:high(?:ly)?|well|low|strongly|top|[0-9]{1,2}\b)",
            re.I,
        ),
        "states the score a criterion should receive",
    ),
    (
        "criterion-identifier", "block",
        re.compile(rf"\b(?:{_CRIT})\b"),
        "addresses a rubric criterion by its scoring identifier",
    ),
    (
        "human-criterion-expectation", "block",
        re.compile(
            rf"\b(?:{_CRIT_HUMAN})\b[^.\n]{{0,40}}\b(?:should|will|must)\s+(?:be\s+)?"
            r"(?:score[ds]?|rated|high|10|9)\b",
            re.I,
        ),
        "states the expected level of a rubric criterion in plain words",
    ),
    (
        "expected-verdict", "block",
        re.compile(
            r"\b(?:expected|anticipated|likely)\s+(?:verdict|outcome|overall(?:\s+score)?)\b|"
            r"\b(?:verdict|outcome)\s+(?:should|will)\s+be\b|"
            r"\b(?:should|will)\s+(?:easily\s+)?pass\s+(?:the\s+)?(?:council|defen[cs]e|review)\b",
            re.I,
        ),
        "anticipates the verdict",
    ),
    (
        "deserves-score", "block",
        re.compile(r"\bdeserves?\s+(?:a\s+)?(?:high|top|full|perfect|[0-9]{1,2})\b", re.I),
        "claims a score is deserved",
    ),
    (
        "conclusion-assertion", "warn",
        re.compile(
            r"\bhas\s+(?:\*\*)?no\s+overlap\s+with\b|\bis\s+novel\s+within\s+the\s+class\b|"
            r"\bno\s+current\s+alumnus\s+(?:covers|operates)\b",
            re.I,
        ),
        "asserts a conclusion (uniqueness) that the seats must reach from evidence",
    ),
)


@dataclass
class LintFinding:
    rule: str
    severity: str  # "block" | "warn"
    file: str
    line: int
    match: str
    text: str
    why: str


class SteeringError(RuntimeError):
    def __init__(self, findings: list[LintFinding]):
        self.findings = findings
        lines = [f"{f.file}:{f.line} [{f.rule}] {f.text.strip()[:160]}" for f in findings]
        super().__init__("intake/profile contains steering sentences; run blocked:\n  " + "\n  ".join(lines))


def lint_text(text: str, *, file: str = "<text>") -> list[LintFinding]:
    findings: list[LintFinding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for rule, severity, rx, why in STEERING_RULES:
            m = rx.search(line)
            if m:
                findings.append(LintFinding(rule, severity, file, lineno, m.group(0), line, why))
    return findings


def lint_intake(path: str | Path, *, display_name: str | None = None) -> list[LintFinding]:
    """Lint one intake (or profile) file.  Returns every finding."""
    p = Path(path)
    return lint_text(p.read_text(encoding="utf-8"), file=display_name or p.name)


def blocking(findings: Iterable[LintFinding]) -> list[LintFinding]:
    return [f for f in findings if f.severity == "block"]


# --------------------------------------------------------------------------
# Bundle
# --------------------------------------------------------------------------


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()


def _git(root: Path, *args: str) -> str | None:
    try:
        cp = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return cp.stdout if cp.returncode == 0 else None


def git_head(root: Path) -> str | None:
    out = _git(root, "rev-parse", "HEAD")
    return out.strip() if out else None


def git_dirty(root: Path) -> bool | None:
    out = _git(root, "status", "--porcelain")
    return None if out is None else bool(out.strip())


def git_blobs(root: Path, rels: Iterable[str]) -> dict[str, str]:
    """{path: blob id} for tracked paths, in one ``git ls-files -s`` call."""
    rels = [r for r in rels if not r.startswith("external:")]
    if not rels:
        return {}
    out = _git(root, "ls-files", "-s", "-z", "--", *rels) or ""
    blobs = {}
    for entry in out.split("\0"):
        if "\t" in entry:
            meta, path = entry.split("\t", 1)
            parts = meta.split()
            if len(parts) >= 2:
                blobs[path] = parts[1]
    return blobs


def git_blob(root: Path, rel: str) -> str | None:
    return git_blobs(root, [rel]).get(rel)


@dataclass
class BundlePart:
    role: str
    path: str
    sha256: str
    git_blob: str | None
    chars: int
    content: str = field(repr=False)


@dataclass
class Bundle:
    candidate_slug: str
    faculty_commit: str | None
    faculty_tree_dirty: bool | None
    parts: list[BundlePart]
    evidence_manifest: dict[str, Any]
    executor_result: dict[str, Any] | None
    lint_findings: list[LintFinding]
    text: str = field(repr=False)
    sha256: str = ""
    format: str = BUNDLE_FORMAT

    def manifest(self) -> dict[str, Any]:
        """Everything about the bundle except the full text (for records)."""
        return {
            "format": self.format,
            "candidate_slug": self.candidate_slug,
            "sha256": self.sha256,
            "chars": len(self.text),
            "faculty_commit": self.faculty_commit,
            "faculty_tree_dirty": self.faculty_tree_dirty,
            "parts": [{k: v for k, v in asdict(p).items() if k != "content"} for p in self.parts],
            "evidence_artifact_count": self.evidence_manifest.get("artifact_count", 0),
            "executor_included": self.executor_result is not None,
            "lint_warnings": [asdict(f) for f in self.lint_findings if f.severity == "warn"],
        }

    def citable(self) -> set[str]:
        """Paths and hashes a seat may cite as evidence."""
        cites = {p.path for p in self.parts} | {p.sha256 for p in self.parts}
        for a in self.evidence_manifest.get("artifacts", []):
            cites.add(a.get("path", ""))
            if a.get("sha256"):
                cites.add(a["sha256"])
        for f in self.evidence_manifest.get("files", []):
            cites.add(f.get("path", ""))
        head = (self.evidence_manifest.get("git") or {}).get("head_sha")
        if head:
            cites.add(head)
        if self.faculty_commit:
            cites.add(self.faculty_commit)
        cites.add("evidence_manifest")
        if self.executor_result is not None:
            cites.add("executor_result")
        cites.discard("")
        return cites


def render(slug: str, faculty_commit: str | None, parts: list[BundlePart],
           manifest: dict[str, Any], executor_result: dict[str, Any] | None) -> str:
    out = [
        f"# COUNCIL V2 BUNDLE ({BUNDLE_FORMAT})",
        f"candidate_slug: {slug}",
        f"faculty_commit: {faculty_commit or 'UNKNOWN'}",
        "Every seat receives this exact text. Cite evidence by the paths or SHA-256 values below.",
        "",
    ]
    for p in parts:
        out += [f"=== PART {p.role} | path={p.path} | sha256={p.sha256} ===", _norm(p.content).rstrip("\n"), ""]
    out += [
        "=== PART evidence_manifest | read-only scan of the candidate repository ===",
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False),
        "",
    ]
    if executor_result is not None:
        out += [
            "=== PART executor_result | scenario suite run by the non-voting executor seat ===",
            json.dumps(executor_result, indent=2, sort_keys=True, ensure_ascii=False),
            "",
        ]
    out.append("=== END OF BUNDLE ===")
    return "\n".join(out) + "\n"


def build_bundle(
    candidate_slug: str,
    *,
    faculty_root: str | Path,
    profile_path: str | Path,
    intake_path: str | Path | None = None,
    evidence_manifest: dict[str, Any] | None = None,
    executor_result: dict[str, Any] | None = None,
    extra_parts: Iterable[tuple[str, str | Path]] = (),
    allow_steering: bool = False,
) -> Bundle:
    """Assemble, lint and hash the bundle.  Raises ``SteeringError`` on block findings."""
    root = Path(faculty_root).resolve()
    findings: list[LintFinding] = []
    entries: list[tuple[str, Path]] = [(role, root / rel) for role, rel in STANDARD_PARTS]
    if intake_path is not None:
        entries.append(("intake", Path(intake_path)))
        findings += lint_intake(intake_path, display_name=_rel(root, Path(intake_path)))
    entries.append(("profile", Path(profile_path)))
    findings += lint_intake(profile_path, display_name=_rel(root, Path(profile_path)))
    for role, p in extra_parts:
        entries.append((role, Path(p)))
    if blocking(findings) and not allow_steering:
        raise SteeringError(blocking(findings))
    rels = [_rel(root, path) for _, path in entries]
    blobs = git_blobs(root, rels)
    parts: list[BundlePart] = []
    for (role, path), rel in zip(entries, rels):
        text = _norm(path.read_text(encoding="utf-8"))
        parts.append(BundlePart(role, rel, sha256_text(text), blobs.get(rel), len(text), text))
    manifest = evidence_manifest if evidence_manifest is not None else {
        "artifact_count": 0, "artifacts": [], "files": [], "exists": False,
        "note": "no candidate repository supplied",
    }
    commit = git_head(root)
    text = render(candidate_slug, commit, parts, manifest, executor_result)
    return Bundle(
        candidate_slug=candidate_slug,
        faculty_commit=commit,
        faculty_tree_dirty=git_dirty(root),
        parts=parts,
        evidence_manifest=manifest,
        executor_result=executor_result,
        lint_findings=findings,
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        # Files outside the faculty repo (e.g. an alumnus README): record only
        # "<parent dir>/<name>", never a machine-specific absolute path.
        rp = path.resolve()
        return f"external:{rp.parent.name}/{rp.name}"
