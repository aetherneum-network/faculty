#!/usr/bin/env python3
"""Generate the Registry table (Markdown + HTML fragment) from signed Council records ONLY.

A record whose Ed25519 signature does not verify against the configured
public key is rejected and listed; it never contributes a number.  Every
score shown is recomputed from the record's raw scores (council_v2.scoring),
so the Registry cannot display a score that no record contains.

Usage::

    python scripts/build_registry.py --records council_v2/ledger \\
        --public-key council_v2/keys/<label>.pub \\
        --out-md registry_v2.md --out-html registry_v2_fragment.html

The public key can also come from AETHERNEUM_COUNCIL_PUBKEY.  Exit code 1 if
any record was rejected and --strict is given.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

FACULTY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FACULTY))

from council_v2 import registry  # noqa: E402
from council_v2.signing import default_public_key_path, load_public_key  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--records", type=Path, nargs="+", required=True, help="directories (or files) of signed records")
    ap.add_argument("--public-key", type=Path, default=default_public_key_path())
    ap.add_argument("--council", type=Path, default=FACULTY / "council" / "council.json")
    ap.add_argument("--out-md", type=Path)
    ap.add_argument("--out-html", type=Path)
    ap.add_argument("--include-mock", action="store_true", help="include dry-run/mock records (never for publication)")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any record is rejected")
    args = ap.parse_args(argv)
    if args.public_key is None:
        print("error: no public key (--public-key or AETHERNEUM_COUNCIL_PUBKEY)", file=sys.stderr)
        return 2
    council = registry.load_council(args.council)
    rows, rejected = registry.build(args.records, load_public_key(args.public_key), council, include_mock=args.include_mock)
    md = registry.to_markdown(rows, council, rejected)
    if args.out_md:
        args.out_md.write_text(md, encoding="utf-8")
    if args.out_html:
        args.out_html.write_text(registry.to_html(rows, council), encoding="utf-8")
    if not args.out_md:
        sys.stdout.reconfigure(encoding="utf-8")
        print(md)
    for f, why in rejected:
        print(f"rejected: {f}: {why}", file=sys.stderr)
    print(f"{len(rows)} row(s), {len(rejected)} rejected record(s)", file=sys.stderr)
    return 1 if (args.strict and rejected) else 0


if __name__ == "__main__":
    raise SystemExit(main())
