#!/usr/bin/env python3
"""
run_council.py — Orchestratore Council multi-model per Step 4 (Defense).

Legge intake + bozza profilo di un candidato, costruisce il bundle, invia in
parallelo a 4 reviewer (Anthropic Chair, Groq Velocity, Cerebras Reasoning,
Moonshot Long-context). Salva i JSON conformi a
templates/COUNCIL_REVIEW_TEMPLATE.json in cohort-<period>/council-reviews/.

Usage:
    python run_council.py --slug tomas-aurelio \\
        --intake intake/tomas-aurelio.md \\
        --profile ../alumni/pending/tomas-aurelio.md \\
        --out council-reviews

Le 4 API key sono lette da .env nella repo root (gitignored).
"""

import os
import sys
import json
import argparse
import concurrent.futures
from pathlib import Path
from datetime import datetime, timezone

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
except ImportError:
    pass

# Force UTF-8 stdout on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent

BUNDLE_FILES = [
    "charter/CHARTER.md",
    "charter/FACULTY_BOARD.md",
    "admission/RUBRIC.md",
    "alumni/_ROSTER.md",
    "templates/COUNCIL_REVIEW_TEMPLATE.json",
]

REVIEWERS = {
    "anthropic_chair": {
        "endpoint": "https://api.anthropic.com/v1/messages",
        "model": os.getenv("ANTHROPIC_COUNCIL_MODEL", "claude-sonnet-4-5-20250929"),
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "provider": "anthropic",
        "name": "Faculty Chair",
        "focus": "coerenza con il Charter e con la voce della Class corrente",
    },
    "groq_velocity": {
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "api_key": os.getenv("GROQ_API_KEY"),
        "provider": "groq",
        "name": "Velocity",
        "focus": "decisioni rapide su prompt operativi, body-of-work density",
    },
    "cerebras_reasoning": {
        "endpoint": "https://api.cerebras.ai/v1/chat/completions",
        "model": os.getenv("CEREBRAS_MODEL", "qwen-3-235b-a22b-instruct-2507"),
        "api_key": os.getenv("CEREBRAS_API_KEY"),
        "provider": "cerebras",
        "name": "Reasoning at scale",
        "focus": "edge cases, dilemmi etici, contraddizioni nel body of work",
    },
    "moonshot_longctx": {
        "endpoint": "https://api.moonshot.ai/v1/chat/completions",
        "model": os.getenv("MOONSHOT_MODEL", "kimi-k2-0905-preview"),
        "api_key": os.getenv("MOONSHOT_API_KEY"),
        "provider": "moonshot",
        "name": "Long context",
        "focus": "coerenza narrativa sull'intero intake e gli artifact citati",
    },
}

SYSTEM_PROMPT = """\
You are a member of the Aetherneum University Faculty Board, participating in a
Council Review (Step 4 — Defense) for the admission of a synthetic alumnus to
the Class of '26.

Your reviewer identity:
- Name: {reviewer_name}
- Provider: {reviewer_provider}
- Model: {reviewer_model}
- Focus: {focus}

Your task: read the bundle that follows, then produce a SINGLE JSON object
strictly conforming to the schema in `templates/COUNCIL_REVIEW_TEMPLATE.json`.
Do not output anything outside the JSON — no preamble, no markdown fences.

Score each of the 7 criteria from 0 to 10, with a 1-3 sentence rationale that
cites the intake or the draft profile. Apply the veto rules described in
RUBRIC.md (synthetic_transparency < 9, body_of_work_depth < 5, or
specialty_uniqueness < 5 trigger an automatic FAIL even if the average is
above 7).

Be honest. Dissent is welcome. If you fail the candidate, state why in the
`dissent` field and list specific revisions in `revisions_required` (empty
array if PASS or FAIL without revision path).

The `review_date` must be ISO 8601 in UTC: "{review_date}".
"""

def build_bundle(candidate_slug, intake_path, profile_path, mode="full"):
    """Build bundle for a reviewer.

    mode: "full" (all references), "compact" (rubric + template),
          "mini" (template only — for narrow-context tier-1 reviewers)
    """
    parts = [f"# CANDIDATE\n\nSlug: `{candidate_slug}`\n"]
    parts.append(f"# INTAKE\n\n{intake_path.read_text(encoding='utf-8')}\n")
    parts.append(f"# DRAFT PROFILE\n\n{profile_path.read_text(encoding='utf-8')}\n")
    if mode == "full":
        files = BUNDLE_FILES
    elif mode == "compact":
        files = ["admission/RUBRIC.md", "templates/COUNCIL_REVIEW_TEMPLATE.json"]
    else:  # mini
        files = ["templates/COUNCIL_REVIEW_TEMPLATE.json"]
    for f in files:
        fp = REPO_ROOT / f
        if fp.exists():
            parts.append(f"# REFERENCE - {f}\n\n{fp.read_text(encoding='utf-8')}\n")
    return "\n\n---\n\n".join(parts)

import time

def _post_with_retry(url, headers, payload, max_attempts=4):
    """POST with exponential backoff on 429/5xx."""
    delay = 4
    for attempt in range(1, max_attempts + 1):
        r = requests.post(url, headers=headers, json=payload, timeout=180)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts:
            time.sleep(delay)
            delay *= 2
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r

def call_reviewer(reviewer_id, cfg, bundle, review_date, startup_delay=0):
    if not cfg["api_key"]:
        raise RuntimeError(f"API key missing for {reviewer_id}")

    # Stagger reviewers with tight RPM (Cerebras) to avoid race
    if startup_delay > 0:
        time.sleep(startup_delay)

    system = SYSTEM_PROMPT.format(
        reviewer_name=cfg["name"],
        reviewer_provider=cfg["provider"],
        reviewer_model=cfg["model"],
        focus=cfg["focus"],
        review_date=review_date,
    )

    if cfg["provider"] == "anthropic":
        r = _post_with_retry(
            cfg["endpoint"],
            headers={
                "x-api-key": cfg["api_key"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            payload={
                "model": cfg["model"],
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": bundle}],
            },
        )
        text = r.json()["content"][0]["text"]
    else:
        r = _post_with_retry(
            cfg["endpoint"],
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            payload={
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": bundle},
                ],
                "max_tokens": 4096,
                "temperature": 0.3,
            },
        )
        text = r.json()["choices"][0]["message"]["content"]

    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if not l.startswith("```"))
    # Robust JSON extraction: find first balanced {...} block if there's surrounding prose
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try balanced-brace extraction first
        start = text.find("{")
        if start >= 0:
            depth = 0
            in_str = False
            escape = False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[start:i+1])
                            except json.JSONDecodeError:
                                break
        # Save raw for debug + re-raise
        debug_path = Path("__last_raw_response__.txt")
        debug_path.write_text(text, encoding="utf-8")
        raise

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--intake", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    intake = Path(args.intake)
    profile = Path(args.profile)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    review_date = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bundle_full = build_bundle(args.slug, intake, profile, mode="full")
    bundle_compact = build_bundle(args.slug, intake, profile, mode="compact")
    bundle_mini = build_bundle(args.slug, intake, profile, mode="mini")
    print(f"[bundle] full={len(bundle_full):,} compact={len(bundle_compact):,} mini={len(bundle_mini):,} chars review_date={review_date}")
    print(f"[council] dispatching to {len(REVIEWERS)} reviewers in parallel")

    # Per-reviewer bundle sizing (Groq free tier has tight payload limit)
    bundle_per_reviewer = {
        "anthropic_chair": bundle_full,
        "moonshot_longctx": bundle_full,
        "cerebras_reasoning": bundle_full,
        "groq_velocity": bundle_mini,  # tightest free-tier token limit
    }
    # Per-reviewer startup delay (stagger Cerebras to avoid RPM race)
    startup_delay = {"cerebras_reasoning": 15}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(call_reviewer, rid, cfg, bundle_per_reviewer[rid], review_date, startup_delay.get(rid, 0)): rid
            for rid, cfg in REVIEWERS.items()
        }
        results = {}
        for fut in concurrent.futures.as_completed(futures):
            rid = futures[fut]
            try:
                result = fut.result()
                out = out_dir / f"{args.slug}__{rid}.json"
                out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
                verdict = result.get("verdict", "?")
                score = result.get("overall_score", "?")
                results[rid] = (verdict, score)
                print(f"[{rid}] OK · verdict={verdict} overall={score} → {out.name}")
            except Exception as e:
                print(f"[{rid}] ERRORE: {type(e).__name__}: {e}")

    print()
    print("=== COUNCIL SUMMARY ===")
    for rid, (v, s) in results.items():
        print(f"  {rid:25s} {v:25s} {s}")
    print()
    passing = sum(1 for v, _ in results.values() if v == "PASS")
    if passing >= 3:
        print(f"OUTCOME: PASS ({passing}/{len(results)} reviewers PASS) → procede a Patron Approval")
    else:
        print(f"OUTCOME: NEEDS WORK ({passing}/{len(results)} reviewers PASS)")

if __name__ == "__main__":
    main()
