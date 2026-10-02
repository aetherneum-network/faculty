#!/usr/bin/env python3
"""Compare alumni/alumni.json with site pages, alumnus READMEs and diploma SVGs.

Prints every divergence (MISMATCH, UNRESOLVED, STALE, REGISTRY, POLICY,
MISSING — see council_v2/consistency.py) and exits 1 if there is any.

Read-only.  Expects the sibling clones next to the faculty repository::

    repos/
      faculty/ (this repo)   aetherneum-sites/   registry/   marco-aurelius/ ...

Usage::

    python scripts/check_consistency.py [--repos-root ..] [--ref main] [--json report.json] [--only <slug>]

Without --ref the checked-out working trees are compared (what CI checks
out); with --ref the given commit of each sibling repository is read via
``git show`` without touching its working tree.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FACULTY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACULTY))

from council_v2 import consistency  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--alumni", type=Path, default=FACULTY / "alumni" / "alumni.json")
    ap.add_argument("--repos-root", type=Path, default=FACULTY.parent)
    ap.add_argument("--ref", default=None, help="read sibling repos at this ref (default: working trees)")
    ap.add_argument("--json", type=Path, help="also write the divergences as JSON")
    ap.add_argument("--only", help="check one slug")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass
    doc = json.loads(args.alumni.read_text(encoding="utf-8"))
    divs = consistency.check_all(doc, repos_root=args.repos_root.resolve(), faculty_root=FACULTY, ref=args.ref, only=args.only)
    for d in divs:
        print(d.line())
    s = consistency.summary(divs)
    print(f"\n{len(divs)} divergence(s): " + (", ".join(f"{k}={v}" for k, v in s.items()) or "none"))
    if args.json:
        args.json.write_text(json.dumps(consistency.to_json(divs), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 1 if divs else 0


if __name__ == "__main__":
    raise SystemExit(main())
