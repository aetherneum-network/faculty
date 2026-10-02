"""Executor seat: run the candidate's scenario suite and count pass/fail.

Council v2 rule 3 (review 2026-09-30 §3): "Un seggio esecutore ... lancia la
suite di scenari dell'alumnus. L'esito passa/fallisce entra nel body of work."

The executor is a *non-voting* seat.  It gives no rubric scores; its result
is written into the bundle (so every voting seat sees the same run) and into
its own signed record.

Scenario convention (one directory per scenario)::

    scenarios/<id>/scenario.json   {"run": ["python", "run.py"], "timeout_s": 60, "expect_exit": 0}
    scenarios/<id>/run.py          used when there is no scenario.json
    scenarios/<id>/run             executable script (POSIX only; skipped with an error on Windows)
    scenarios/<id>/test_*.py       run with pytest if installed, else unittest

A scenario passes when its process exits with ``expect_exit`` (default 0)
within the timeout.

Containment ("never runs anything outside the given repo path")
---------------------------------------------------------------
* every scenario directory must resolve inside the repository root
  (symlinks that escape are rejected);
* the working directory is the scenario directory;
* the program is either this Python interpreter (``python``/``python3`` are
  mapped to ``sys.executable``) running a script or module *inside the
  repository*, or an executable file inside the repository; any other
  program (``npm``, ``bash -c``, absolute paths elsewhere) is rejected;
* the child environment is minimal: variables whose names contain KEY,
  TOKEN, SECRET, PASSWORD or CREDENTIAL are never passed.

This is containment of *what is launched*, not a sandbox: launched code runs
with the caller's OS permissions.  For untrusted candidate repositories run
the executor inside a disposable container or CI runner (see README.md).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_S = 60
MAX_OUTPUT_CHARS = 4000
SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.I)
PY_ALIASES = {"python", "python3", "py"}


class ContainmentError(ValueError):
    pass


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _child_env() -> dict[str, str]:
    keep = ("PATH", "SYSTEMROOT", "SystemRoot", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "LANG", "PYTHONIOENCODING")
    env = {k: v for k, v in os.environ.items() if k in keep and not SECRET_ENV.search(k)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _have_pytest() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("pytest") is not None
    except Exception:  # pragma: no cover
        return False


def resolve_command(repo: Path, scen_dir: Path) -> tuple[list[str], dict[str, Any]]:
    """Return (argv, spec) for one scenario, or raise ContainmentError."""
    spec: dict[str, Any] = {"timeout_s": DEFAULT_TIMEOUT_S, "expect_exit": 0}
    cfg = scen_dir / "scenario.json"
    if cfg.is_file():
        data = json.loads(cfg.read_text(encoding="utf-8"))
        spec.update({k: data[k] for k in ("timeout_s", "expect_exit") if k in data})
        argv = data.get("run")
        if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
            raise ContainmentError("scenario.json 'run' must be a non-empty list of strings")
    elif (scen_dir / "run.py").is_file():
        argv = ["python", "run.py"]
    elif (scen_dir / "run").is_file():
        if os.name == "nt":
            raise ContainmentError("'run' scripts are POSIX-only; provide run.py or scenario.json")
        argv = ["./run"]
    elif any(scen_dir.glob("test_*.py")):
        argv = ["python", "-m", "pytest" if _have_pytest() else "unittest"]
        argv += ["-q", "."] if _have_pytest() else ["discover", "-s", ".", "-p", "test_*.py"]
    else:
        raise ContainmentError("no run.py, run, scenario.json or test_*.py")

    prog, rest = argv[0], argv[1:]
    if prog in PY_ALIASES:
        if rest and rest[0] == "-m":
            if len(rest) < 2 or rest[1] not in ("pytest", "unittest"):
                raise ContainmentError("only 'python -m pytest' or 'python -m unittest' are allowed")
        elif rest:
            target = (scen_dir / rest[0])
            if not _inside(repo, target) or not target.is_file():
                raise ContainmentError(f"script {rest[0]!r} is not a file inside the repository")
        else:
            raise ContainmentError("bare interpreter without a script")
        return [sys.executable, *rest], spec
    target = scen_dir / prog
    if not _inside(repo, target) or not target.is_file():
        raise ContainmentError(f"program {prog!r} is outside the repository or not a file")
    return [str(target.resolve()), *rest], spec


@dataclass
class ScenarioResult:
    scenario_id: str
    status: str  # "pass" | "fail" | "error" | "timeout"
    exit_code: int | None
    duration_s: float
    command: list[str]
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None


@dataclass
class ExecutorResult:
    repo: str
    head_sha: str | None
    scenarios_found: int
    passed: int
    failed: int
    errors: int
    timeouts: int
    results: list[ScenarioResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    python: str = sys.version.split()[0]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _display_cmd(argv: list[str], repo: Path) -> list[str]:
    """Record commands without machine-specific absolute paths."""
    out = []
    for a in argv:
        if a == sys.executable:
            out.append("python")
            continue
        try:
            out.append(Path(a).resolve().relative_to(repo.resolve()).as_posix())
        except (ValueError, OSError):
            out.append(a)
    return out


def run_scenarios(repo_path: str | Path, *, timeout_s: int | None = None, head_sha: str | None = None) -> ExecutorResult:
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise ContainmentError(f"repository path {repo_path} does not exist")
    started = _now()
    results: list[ScenarioResult] = []
    root = repo / "scenarios"
    dirs = []
    if root.is_dir():
        dirs = sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith((".", "_")))
    for d in dirs:
        sid = d.name
        if not _inside(repo, d):
            results.append(ScenarioResult(sid, "error", None, 0.0, [], error="scenario directory escapes the repository"))
            continue
        try:
            argv, spec = resolve_command(repo, d)
        except (ContainmentError, json.JSONDecodeError) as e:
            results.append(ScenarioResult(sid, "error", None, 0.0, [], error=str(e)))
            continue
        limit = timeout_s if timeout_s is not None else int(spec.get("timeout_s", DEFAULT_TIMEOUT_S))
        t0 = time.monotonic()
        try:
            cp = subprocess.run(
                argv, cwd=str(d), env=_child_env(), capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=limit,
                stdin=subprocess.DEVNULL,
            )
            dt = round(time.monotonic() - t0, 3)
            ok = cp.returncode == int(spec.get("expect_exit", 0))
            results.append(ScenarioResult(
                sid, "pass" if ok else "fail", cp.returncode, dt, _display_cmd(argv, repo),
                (cp.stdout or "")[-MAX_OUTPUT_CHARS:], (cp.stderr or "")[-MAX_OUTPUT_CHARS:],
            ))
        except subprocess.TimeoutExpired:
            dt = round(time.monotonic() - t0, 3)
            results.append(ScenarioResult(sid, "timeout", None, dt, _display_cmd(argv, repo), error=f"timeout after {limit}s"))
        except OSError as e:
            results.append(ScenarioResult(sid, "error", None, 0.0, _display_cmd(argv, repo), error=f"{type(e).__name__}: {e}"))
    return ExecutorResult(
        repo=repo.name,
        head_sha=head_sha,
        scenarios_found=len(dirs),
        passed=sum(r.status == "pass" for r in results),
        failed=sum(r.status == "fail" for r in results),
        errors=sum(r.status == "error" for r in results),
        timeouts=sum(r.status == "timeout" for r in results),
        results=results,
        started_at=started,
        finished_at=_now(),
    )
