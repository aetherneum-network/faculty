#!/usr/bin/env python3
"""
council.py — the Aetherneum multi-vendor admission Council, runnable.

Four independent model families score one candidate against one seven-criterion
rubric. Each writes a JSON verdict in the *exact* schema committed under
``cohort-phase-0/council-reviews/``. A quorum of PASS verdicts admits.

No single model certifies another: where the four disagree, the split is kept,
not smoothed over. That is the whole point.

    Read the commits. Then re-run them:

        pip install requests
        export ANTHROPIC_API_KEY=...   CEREBRAS_API_KEY=...
        export MOONSHOT_API_KEY=...    GROQ_API_KEY=...
        python council.py candidates/elena-tessera.md

Outputs one ``<slug>__<provider>_<role>.json`` per reviewer to ``./out/`` and
prints the quorum verdict. LLMs are stochastic — your scores will differ
run-to-run. The point is that the process and the format are open and
reproducible, not that the numbers are frozen.

MIT licensed. Per Æthera Ad Astra.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests  # the only dependency

OUT = Path(__file__).parent / "out"

# ── The seven rubric criteria (admission/RUBRIC.md) ────────────────────────────
# Score each 0–10. Pass threshold: mean ≥ 7 across all criteria AND no criterion
# below 5. Two are veto criteria: synthetic_transparency and body_of_work_depth.
CRITERIA = {
    "body_of_work_depth":        "Is there a real, traceable, verifiable corpus of work (artifacts, repos, deploys), not a single script or unproven claims?",
    "specialty_uniqueness":      "Does the specialty cover a real gap in the current Class, evocatively named, coherent with the body of work, without overlap?",
    "voice_personality_clarity": "Is the voice recognizable and specific? Can you imagine what this alumnus would refuse to do?",
    "faithful_distillation":     "Is the profile faithful to the actual work, or does it embroider beyond what was really done?",
    "synthetic_transparency":    "Does the profile declare it is synthetic, unambiguously, in compliance with Charter principle #1? (VETO criterion)",
    "placement_fit":             "Is the operating placement concrete and well-defined, with real territory rather than abstraction?",
    "continuity_with_class":     "Does the name, motto, diploma and avatar follow the Class of '26 conventions and voice?",
}
PASS_MEAN = 7.0
PASS_FLOOR = 5.0

# ── The four-vendor Council. No single model certifies another. ────────────────
# model env-overridable so a stale id never blocks a re-run.
REVIEWERS = [
    {
        "name": "Faculty Chair", "provider": "anthropic", "role": "chair",
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        "key_env": "ANTHROPIC_API_KEY",
        "kind": "anthropic",
        "url": "https://api.anthropic.com/v1/messages",
    },
    {
        "name": "Reasoning at Scale", "provider": "cerebras", "role": "reasoning",
        "model": os.environ.get("CEREBRAS_MODEL", "qwen-3-235b-a22b-instruct"),
        "key_env": "CEREBRAS_API_KEY",
        "kind": "openai",
        "url": "https://api.cerebras.ai/v1/chat/completions",
    },
    {
        "name": "Long Context", "provider": "moonshot", "role": "longctx",
        "model": os.environ.get("MOONSHOT_MODEL", "kimi-k2-0711-preview"),
        "key_env": "MOONSHOT_API_KEY",
        "kind": "openai",
        "url": "https://api.moonshot.ai/v1/chat/completions",
    },
    {
        "name": "Velocity", "provider": "groq", "role": "velocity",
        "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "key_env": "GROQ_API_KEY",
        "kind": "openai",
        "url": "https://api.groq.com/openai/v1/chat/completions",
    },
]


def build_prompt(dossier: str) -> str:
    crit = "\n".join(f"- {k}: {v}" for k, v in CRITERIA.items())
    keys = ", ".join(CRITERIA)
    return (
        "You sit on the Aetherneum admission Council. Score the candidate below "
        "against the seven criteria, each 0-10 (0 unsatisfactory, 10 paradigmatic), "
        "with a 1-3 sentence rationale per criterion grounded in the dossier.\n\n"
        f"CRITERIA:\n{crit}\n\n"
        "Pass threshold: mean >= 7 across all criteria AND no criterion below 5. "
        "synthetic_transparency and body_of_work_depth are veto criteria; if either "
        "is below 5 the verdict cannot be PASS.\n\n"
        "Return STRICT JSON only, no prose around it, with exactly these keys:\n"
        '{ "criterion_scores": { ' + keys + ': {"score": int, "rationale": str} }, '
        '"verdict": "PASS"|"REVISE"|"FAIL", "dissent": str|null, '
        '"revisions_required": [str], "notes": str }\n\n'
        f"CANDIDATE DOSSIER:\n{dossier}"
    )


def call_anthropic(r: dict, key: str, prompt: str) -> str:
    resp = requests.post(
        r["url"],
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": r["model"], "max_tokens": 2000,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def call_openai_compatible(r: dict, key: str, prompt: str) -> str:
    resp = requests.post(
        r["url"],
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": r["model"], "temperature": 0.4,
              "messages": [
                  {"role": "system", "content": "You are a rigorous admission reviewer. Return only valid JSON."},
                  {"role": "user", "content": prompt}]},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


def aggregate(scores: dict) -> tuple[float, float, str]:
    vals = [c["score"] for c in scores.values()]
    mean = round(sum(vals) / len(vals), 2)
    floor = min(vals)
    veto_ok = scores["synthetic_transparency"]["score"] >= PASS_FLOOR and \
        scores["body_of_work_depth"]["score"] >= PASS_FLOOR
    verdict = "PASS" if (mean >= PASS_MEAN and floor >= PASS_FLOOR and veto_ok) else "FAIL"
    return mean, floor, verdict


def review(r: dict, slug: str, specialty: str, thesis: str, dossier: str) -> dict | None:
    key = os.environ.get(r["key_env"])
    if not key:
        print(f"  - {r['provider']:<9} SKIP (no {r['key_env']})")
        return None
    prompt = build_prompt(dossier)
    try:
        raw = (call_anthropic if r["kind"] == "anthropic" else call_openai_compatible)(r, key, prompt)
        parsed = extract_json(raw)
    except Exception as e:
        print(f"  - {r['provider']:<9} ERROR {str(e)[:80]}")
        return None

    scores = parsed["criterion_scores"]
    mean, floor, computed = aggregate(scores)
    out = {
        "reviewer_name": r["name"],
        "reviewer_model": r["model"],
        "reviewer_provider": r["provider"],
        "review_date": datetime.now(timezone.utc).isoformat(),
        "candidate_slug": slug,
        "candidate_specialty": specialty,
        "candidate_master_thesis": thesis,
        "criterion_scores": scores,
        "overall_score": mean,
        "verdict": parsed.get("verdict", computed),
        "dissent": parsed.get("dissent"),
        "revisions_required": parsed.get("revisions_required", []),
        "notes": parsed.get("notes", ""),
    }
    OUT.mkdir(exist_ok=True)
    fp = OUT / f"{slug}__{r['provider']}_{r['role']}.json"
    fp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  - {r['provider']:<9} {out['verdict']:<6} {mean:>5}/10  → {fp.name}")
    return out


def parse_dossier(path: Path) -> tuple[str, str, str, str]:
    """Slug from filename; specialty + thesis from optional front-matter lines."""
    text = path.read_text(encoding="utf-8")
    slug = path.stem
    spec = re.search(r"(?im)^specialty:\s*(.+)$", text)
    thes = re.search(r"(?im)^thesis:\s*(.+)$", text)
    return (slug,
            spec.group(1).strip() if spec else "(unspecified)",
            thes.group(1).strip() if thes else "(unspecified)",
            text)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python council.py candidates/<slug>.md")
        return 2
    slug, specialty, thesis, dossier = parse_dossier(Path(sys.argv[1]))
    print(f"\n  Aetherneum Council — {slug}\n")
    results = [review(r, slug, specialty, thesis, dossier) for r in REVIEWERS]
    done = [x for x in results if x]
    if not done:
        print("\n  No reviewers ran. Set at least one API key.\n")
        return 1
    passes = sum(1 for x in done if x["verdict"] == "PASS")
    quorum = passes >= max(2, (len(done) // 2) + 1)
    print(f"\n  Quorum: {passes}/{len(done)} PASS → {'ADMIT' if quorum else 'HOLD'}")
    print("  Disagreement is kept, not smoothed. Read the JSONs in ./out/\n")
    print("  Per Æthera Ad Astra.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
