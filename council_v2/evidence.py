"""Read-only scan of an alumnus repository into an artifact manifest.

Council v2 rule 2 (review 2026-09-30 §3): "Si vota sulle prove. Il Council
legge il repository in sola lettura e deve citare un percorso o uno SHA per
ogni affermazione. Con zero artefatti, il body of work non supera 3".

What counts as an artifact (anything that can be executed or checked):

* ``code``      source files (by extension), outside ``scenarios/`` and tests
* ``test``      files under ``tests/``/``test/`` or named ``test_*``/``*_test``/``*.test.*``/``*.spec.*``
* ``ci``        CI configuration (GitHub Actions, GitLab, CircleCI, Azure, Jenkins)
* ``scenario``  each directory ``scenarios/<id>/`` (the executor convention)
* ``release``   git tags, and files under ``releases/``

What does NOT count: README/docs/markdown, LICENSE, images/avatars, dotfiles
such as ``.gitignore``.  A profile is a claim, not a proof.

The scan never writes to the repository and never executes anything; git is
called only with read-only sub-commands (``rev-parse``, ``ls-files``,
``ls-tree``, ``show``, ``tag``, ``log``, ``cat-file``, ``status``).  With
``ref=`` (e.g. ``"main"``) the scan reads that commit instead of the working
tree, so a checkout that another person is editing does not change the result.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

CODE_EXT = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".sol", ".java",
    ".kt", ".kts", ".swift", ".m", ".mm", ".rb", ".php", ".cs", ".c", ".h", ".cpp", ".hpp",
    ".sh", ".ps1", ".sql", ".vy", ".scala", ".dart", ".lua", ".r",
}
CI_PATTERNS = (
    re.compile(r"^\.github/workflows/[^/]+\.ya?ml$"),
    re.compile(r"^\.gitlab-ci\.ya?ml$"),
    re.compile(r"^\.circleci/config\.ya?ml$"),
    re.compile(r"^azure-pipelines\.ya?ml$"),
    re.compile(r"^Jenkinsfile$"),
)
TEST_NAME = re.compile(r"(^|/)(test_[^/]+|[^/]+_test\.[a-z]+|[^/]+\.(test|spec)\.[a-z]+)$")
TEST_DIR = re.compile(r"(^|/)(tests?|__tests__)/")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}
AETHERNEUM_DOMAIN = "@aetherneum.com"
RULE = "zero artifacts => body_of_work_depth capped at 3 (veto)"


def _git_bytes(repo: Path, *args: str) -> bytes | None:
    try:
        cp = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return cp.stdout if cp.returncode == 0 else None


def _git(repo: Path, *args: str) -> str | None:
    out = _git_bytes(repo, *args)
    return None if out is None else out.decode("utf-8", "replace")


def is_git_toplevel(repo: Path) -> bool:
    """True only if ``repo`` is itself the root of a git work tree.

    A plain directory nested inside another repository (e.g. a test fixture)
    must not inherit that repository's commits, tags or identities.
    """
    top = _git(repo, "rev-parse", "--show-toplevel")
    if not top:
        return False
    try:
        return Path(top.strip()).resolve() == Path(repo).resolve()
    except OSError:
        return False


def read_bytes(repo: Path, rel: str, ref: str | None = None) -> bytes | None:
    """File content from the working tree, or from commit ``ref`` (read-only)."""
    if ref:
        return _git_bytes(repo, "show", f"{ref}:{rel}")
    try:
        return (Path(repo) / rel).read_bytes()
    except OSError:
        return None


def _list_files(repo: Path, ref: str | None = None) -> list[str]:
    """Files at ``ref``, tracked files of the work tree, or a filesystem walk."""
    top = is_git_toplevel(repo)
    if ref:
        if not top:
            return []
        out = _git(repo, "ls-tree", "-r", "-z", "--name-only", ref)
        return sorted(p for p in (out or "").split("\0") if p)
    out = _git(repo, "ls-files", "-z") if top else None
    if out is not None and out.strip("\0"):
        return sorted(p for p in out.split("\0") if p)
    files = []
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.is_file():
            files.append(rel.as_posix())
    return files


def classify(rel: str) -> str | None:
    """Return the artifact kind of a repo-relative POSIX path, or None."""
    if any(rx.match(rel) for rx in CI_PATTERNS):
        return "ci"
    if rel.startswith("releases/"):
        return "release"
    if rel.startswith("scenarios/"):
        return None  # scenarios are counted per directory, below
    ext = Path(rel).suffix.lower()
    if TEST_NAME.search(rel) or (TEST_DIR.search(rel) and ext in CODE_EXT):
        return "test"
    if ext in CODE_EXT:
        return "code"
    return None


NON_ALUMNUS = "[non-alumnus identity, redacted]"


def _redact_identity(line: str) -> str:
    """Keep alumnus identities (public by design: ``<first>.<last>@aetherneum.com``).

    Every other identity — name and address — is replaced by one placeholder:
    operator accounts can reveal personal addresses or associations that are
    not for this file (review §8: personal addresses out of the commits).
    """
    m = re.match(r"^(.*?) <([^>]*)>$", line.strip())
    if not m:
        return NON_ALUMNUS
    name, email = m.group(1), m.group(2)
    if email.lower().endswith(AETHERNEUM_DOMAIN) and not email.lower().startswith("aetherneum@"):
        return f"{name} <{email}>"
    return NON_ALUMNUS


def git_facts(repo: Path, ref: str | None = None) -> dict[str, Any]:
    if not is_git_toplevel(repo):
        return {"is_git_repo": False}
    rev = ref or "HEAD"
    head = _git(repo, "rev-parse", rev)
    if head is None:
        return {"is_git_repo": True, "ref": rev, "error": f"unknown ref {rev}"}
    log = _git(repo, "log", "--format=%H%x1f%an <%ae>%x1f%aI", rev) or ""
    commits = [ln.split("\x1f") for ln in log.splitlines() if ln.strip()]
    identities: dict[str, int] = {}
    signed = 0
    for sha, ident, _date in commits:
        red = _redact_identity(ident)
        identities[red] = identities.get(red, 0) + 1
        raw = _git(repo, "cat-file", "commit", sha) or ""
        if "\ngpgsig " in raw or raw.startswith("gpgsig "):
            signed += 1
    tags = [t for t in (_git(repo, "tag", "--merged", rev) or "").splitlines() if t.strip()]
    facts = {
        "is_git_repo": True,
        "ref": rev,
        "head_sha": head.strip(),
        "commit_count": len(commits),
        "first_commit_at": commits[-1][2] if commits else None,
        "last_commit_at": commits[0][2] if commits else None,
        "author_identities": dict(sorted(identities.items())),
        "commits_with_signature_header": signed,
        "tags": tags,
    }
    if ref is None:
        status = _git(repo, "status", "--porcelain")
        facts["working_tree_dirty"] = bool(status and status.strip())
    return facts


def scan_repo(repo_path: str | Path, *, with_git: bool = True, ref: str | None = None) -> dict[str, Any]:
    """Build the artifact manifest of ``repo_path`` (read-only)."""
    repo = Path(repo_path).resolve()
    empty = {
        "repo_path": Path(repo_path).name, "exists": False, "files": [], "artifacts": [],
        "artifact_count": 0, "counts": {}, "scenario_ids": [],
        "has_code": False, "has_tests": False, "has_ci": False, "has_scenarios": False,
        "has_releases": False, "rule": RULE,
    }
    if not repo.is_dir():
        return empty
    files = _list_files(repo, ref)
    artifacts: list[dict[str, Any]] = []
    file_entries = []
    for rel in files:
        data = read_bytes(repo, rel, ref)
        if data is None:
            continue
        entry = {"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        file_entries.append(entry)
        kind = classify(rel)
        if kind:
            artifacts.append({"kind": kind, **entry})
    scenario_ids = sorted({
        rel.split("/")[1] for rel in files
        if rel.startswith("scenarios/") and rel.count("/") >= 2 and not rel.split("/")[1].startswith((".", "_"))
    })
    for sid in scenario_ids:
        n = sum(1 for f in files if f.startswith(f"scenarios/{sid}/"))
        artifacts.append({"kind": "scenario", "path": f"scenarios/{sid}/", "files": n})
    facts = git_facts(repo, ref) if with_git else {"is_git_repo": None}
    for t in facts.get("tags", []) or []:
        artifacts.append({"kind": "release", "path": f"refs/tags/{t}"})
    counts: dict[str, int] = {}
    for a in artifacts:
        counts[a["kind"]] = counts.get(a["kind"], 0) + 1
    return {
        "repo_path": repo.name,
        "exists": True,
        "ref": ref,
        "git": facts,
        "files": file_entries,
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "counts": counts,
        "scenario_ids": scenario_ids,
        "has_code": counts.get("code", 0) > 0,
        "has_tests": counts.get("test", 0) > 0,
        "has_ci": counts.get("ci", 0) > 0,
        "has_scenarios": counts.get("scenario", 0) > 0,
        "has_releases": counts.get("release", 0) > 0,
        "rule": RULE,
    }
