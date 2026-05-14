#!/usr/bin/env python3
"""
run-council-defense.py — Multi-provider Council Defense for the 10 Phase-0
alumni of the Class of '26. Backfills the formal protocol retroactively so
that every alumnus has 4 published JSON peer reviews, matching the protocol
applied to Costanza Notari (the first Q2 candidate conferred under it).

Reviewers:
  - Anthropic Sonnet 4.6   (Faculty Chair)
  - Cerebras Qwen 3 235B   (Reasoning at scale)
  - Moonshot Kimi K2       (Long context)
  - Groq Llama 3.3 70B     (Velocity)

Output: cohort-phase-0/council-reviews/<slug>__<reviewer>.json (40 files)

Run on cryptohost. Reads keys from /opt/aetherneum/apps/mirror-agent/.env.
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ENV_FILE = Path(os.environ.get("ENV_FILE", "/opt/aetherneum/apps/mirror-agent/.env"))
FACULTY = Path(os.environ.get("FACULTY_DIR", "/tmp/faculty-fresh"))
ALUMNI_DIR = Path(os.environ.get("ALUMNI_DIR", "/tmp/alumni-push"))
OUT_DIR = FACULTY / "cohort-phase-0" / "council-reviews"

ALUMNI = [
    "marco-aurelius", "lucia-solari", "riku-aetherian", "adrian-volta",
    "davide-ferri", "elena-tessera", "yara-indrani", "sofia-lume",
    "noa-cifratti", "tariq-al-khwarizmi",
]

REVIEWERS = {
    "anthropic_chair": {
        "name": "Faculty Chair",
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "kind": "anthropic",
        "url": "https://api.anthropic.com/v1/messages",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "cerebras_reasoning": {
        "name": "Reasoning at scale",
        "provider": "cerebras",
        "model": "qwen-3-235b-a22b-instruct-2507",
        "kind": "openai",
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "env_key": "CEREBRAS_API_KEY",
    },
    "moonshot_longctx": {
        "name": "Long context",
        "provider": "moonshot",
        "model": "moonshot-v1-32k",
        "kind": "openai",
        "url": "https://api.moonshot.ai/v1/chat/completions",
        "env_key": "MOONSHOT_API_KEY",
    },
    "groq_velocity": {
        "name": "Velocity",
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "kind": "openai",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "env_key": "GROQ_API_KEY",
    },
}


def load_env() -> None:
    if not ENV_FILE.exists():
        sys.exit(f"missing {ENV_FILE}")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_common_bundle() -> str:
    return f"""# AETHERNEUM CHARTER

{read(FACULTY / 'charter' / 'CHARTER.md')}

---

# FACULTY BOARD

{read(FACULTY / 'charter' / 'FACULTY_BOARD.md')}

---

# RUBRIC (the 7 criteria you will score)

{read(FACULTY / 'admission' / 'RUBRIC.md')}

---

# CURRENT ROSTER (for cross-overlap awareness)

{read(FACULTY / 'alumni' / '_ROSTER.md')}
"""


SYSTEM_PROMPT_TPL = """You are a Faculty Member of the Aetherneum University multi-model Council, sitting in the role of {role_name}. You are reviewing a candidate from the Class of '26 for admission under the formal multi-model Council Defense protocol.

Your output MUST be a single valid JSON object — no markdown fences, no prose outside the JSON. Use this exact shape and field set:

{{
  "criterion_scores": {{
    "body_of_work_depth":       {{"score": <int 0-10>, "rationale": "<2-4 sentences>"}},
    "specialty_uniqueness":     {{"score": <int 0-10>, "rationale": "<2-4 sentences>"}},
    "voice_personality_clarity":{{"score": <int 0-10>, "rationale": "<2-4 sentences>"}},
    "faithful_distillation":    {{"score": <int 0-10>, "rationale": "<2-4 sentences>"}},
    "synthetic_transparency":   {{"score": <int 0-10>, "rationale": "<2-4 sentences>"}},
    "placement_fit":            {{"score": <int 0-10>, "rationale": "<2-4 sentences>"}},
    "continuity_with_class":    {{"score": <int 0-10>, "rationale": "<2-4 sentences>"}}
  }},
  "overall_score": <float, weighted: (depth*1.5 + uniqueness*1.5 + voice*1 + faithful*1 + synthetic*1 + placement*1 + continuity*0.5) / 7.5, round to 2 decimals>,
  "verdict": "PASS" | "PASS_WITH_REVISIONS" | "FAIL",
  "dissent": null | "<one sentence if you dissent from likely majority>",
  "revisions_required": [] | ["<short revision 1>", ...],
  "notes": "<one paragraph (4-6 sentences) summary for the Dean>"
}}

VETO RULES (force verdict=FAIL regardless of overall_score):
- synthetic_transparency < 9
- body_of_work_depth < 5
- specialty_uniqueness < 5

GUIDANCE:
- Evaluate strictly against the Rubric. Be honest, not flattering. A real "9" or "10" must be earned.
- For Phase-0 alumni (the original 10), they were conferred BEFORE this protocol existed — you are reviewing their public profile RETROACTIVELY. Be especially attentive to whether the profile actually backs every claim, since the Dean was the sole reviewer at conferral time.
- Cross-check with the CURRENT ROSTER for specialty overlaps."""


def build_user_message(slug: str, alumnus_md: str, common: str) -> str:
    return f"""# COMMON CONTEXT (Charter + Faculty Board + Rubric + Roster)

{common}

---

# CANDIDATE — {slug}

The public profile (`README.md`) of the candidate is the primary artifact to evaluate. The placement, biography, body of work, voice, skills certificate, diploma, and avatar prompt are all here:

{alumnus_md}

---

# YOUR TASK

Produce the structured JSON review of `{slug}` as specified in your system instructions. Score the 7 criteria. Compute the weighted overall score. Issue a verdict (with veto check). Return ONLY the JSON object."""


# ---- API callers ----

async def _post_with_retry(client: httpx.AsyncClient, url: str, headers: dict, payload: dict, max_attempts: int = 5) -> httpx.Response:
    """POST with exponential backoff on 429 / 5xx / connection errors."""
    backoff = 4.0
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            r = await client.post(url, headers=headers, json=payload, timeout=180)
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            last_err = e
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            last_err = httpx.HTTPStatusError(f"transient {r.status_code}", request=r.request, response=r)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        r.raise_for_status()
        return r
    raise last_err or RuntimeError("retries exhausted")


async def call_anthropic(client: httpx.AsyncClient, url: str, key: str, model: str, system: str, user: str) -> str:
    r = await _post_with_retry(
        client,
        url,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        payload={
            "model": model,
            "max_tokens": 4000,
            "temperature": 0.2,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
    )
    data = r.json()
    return data["content"][0]["text"]


async def call_openai_compat(client: httpx.AsyncClient, url: str, key: str, model: str, system: str, user: str) -> str:
    r = await _post_with_retry(
        client,
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        payload={
            "model": model,
            "temperature": 0.2,
            "max_tokens": 4000,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    )
    data = r.json()
    return data["choices"][0]["message"]["content"]


def extract_json(text: str) -> dict[str, Any]:
    """Tolerant JSON extraction: strip code fences if present, then parse."""
    text = text.strip()
    # Strip ```json ... ``` fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # If still has stray prose before/after, grab the first {...} chunk
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace == -1 or last_brace == -1:
        raise ValueError("no JSON object found in output")
    return json.loads(text[first_brace : last_brace + 1])


# ---- Build the final review object (we wrap the model output with metadata) ----

THESIS_RE = re.compile(r'> \*"([^"]+)"\*', re.MULTILINE)
SPECIALTY_RE = re.compile(r"Master of the &AElig;ther \\u2014 ([^\\n<|]+)|Master of the Æther — ([^\n<|]+)")


def extract_thesis(alumnus_md: str) -> str:
    m = THESIS_RE.search(alumnus_md)
    return m.group(1).strip() if m else "(thesis not found)"


def extract_specialty(alumnus_md: str) -> str:
    for line in alumnus_md.splitlines():
        if "Master of the Æther" in line:
            # e.g. "| 🎓 Master Degree | **Master of the Æther — Surface Resilience** |"
            m = re.search(r"Master of the Æther [—-] ([^|*\n]+)", line)
            if m:
                return m.group(1).strip().rstrip("*").strip()
    return "(specialty not found)"


def wrap_review(slug: str, alumnus_md: str, reviewer_id: str, model_output: dict[str, Any]) -> dict[str, Any]:
    cfg = REVIEWERS[reviewer_id]
    thesis = extract_thesis(alumnus_md)
    specialty = extract_specialty(alumnus_md)
    veto_applied = None
    syn = model_output.get("criterion_scores", {}).get("synthetic_transparency", {}).get("score", 0)
    bod = model_output.get("criterion_scores", {}).get("body_of_work_depth", {}).get("score", 0)
    uni = model_output.get("criterion_scores", {}).get("specialty_uniqueness", {}).get("score", 0)
    if syn < 9:
        veto_applied = "synthetic_transparency < 9 (charter veto)"
    elif bod < 5:
        veto_applied = "body_of_work_depth < 5 (charter veto)"
    elif uni < 5:
        veto_applied = "specialty_uniqueness < 5 (charter veto)"
    verdict = model_output.get("verdict", "UNKNOWN")
    if veto_applied and verdict != "FAIL":
        verdict = "FAIL"
    return {
        "reviewer_name": cfg["name"],
        "reviewer_model": cfg["model"],
        "reviewer_provider": cfg["provider"],
        "review_date": datetime.now(timezone.utc).isoformat(),
        "candidate_slug": slug,
        "candidate_specialty": specialty,
        "candidate_master_thesis": thesis,
        "criterion_scores": model_output["criterion_scores"],
        "overall_score": float(model_output.get("overall_score", 0)),
        "verdict": verdict,
        "dissent": model_output.get("dissent"),
        "revisions_required": model_output.get("revisions_required", []),
        "notes": model_output.get("notes", ""),
        **({"veto_applied": veto_applied} if veto_applied else {}),
    }


# ---- Orchestration ----

async def run_one(client: httpx.AsyncClient, slug: str, alumnus_md: str, common: str, reviewer_id: str) -> tuple[str, str, dict[str, Any] | None, str | None]:
    cfg = REVIEWERS[reviewer_id]
    key = os.environ.get(cfg["env_key"], "")
    if not key:
        return slug, reviewer_id, None, f"missing env {cfg['env_key']}"
    system = SYSTEM_PROMPT_TPL.format(role_name=cfg["name"])
    user = build_user_message(slug, alumnus_md, common)
    # Retry up to 2 times on JSON decode failure (model occasionally emits malformed JSON).
    last_err = None
    for attempt in range(2):
        try:
            if cfg["kind"] == "anthropic":
                raw = await call_anthropic(client, cfg["url"], key, cfg["model"], system, user)
            else:
                raw = await call_openai_compat(client, cfg["url"], key, cfg["model"], system, user)
            try:
                parsed = extract_json(raw)
            except (json.JSONDecodeError, ValueError) as je:
                last_err = f"JSONDecodeError(attempt {attempt + 1}): {je}"
                await asyncio.sleep(2)
                continue
            wrapped = wrap_review(slug, alumnus_md, reviewer_id, parsed)
            return slug, reviewer_id, wrapped, None
        except Exception as e:
            return slug, reviewer_id, None, f"{type(e).__name__}: {e}"
        finally:
            # Small pacing to ease per-provider rate limits between sequential calls
            if reviewer_id in ("cerebras_reasoning", "groq_velocity"):
                await asyncio.sleep(1.5)
    return slug, reviewer_id, None, last_err or "unknown"


async def main():
    load_env()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    common = build_common_bundle()

    # Pre-load all alumnus READMEs
    alumni_md = {}
    for slug in ALUMNI:
        p = ALUMNI_DIR / slug / "README.md"
        if not p.exists():
            sys.exit(f"missing {p}")
        alumni_md[slug] = read(p)

    # Build job list (slug, reviewer_id), skip if output already exists
    jobs = []
    skipped = 0
    for slug in ALUMNI:
        for rid in REVIEWERS:
            out_path = OUT_DIR / f"{slug}__{rid}.json"
            if out_path.exists() and out_path.stat().st_size > 200:
                skipped += 1
                continue
            jobs.append((slug, rid))
    print(f"==> {len(jobs)} reviews to run ({skipped} already exist on disk, skipping)")

    # Per-provider semaphores. Cerebras + Groq have aggressive rate limits
    # (free tier ~30 req/min); serializing them is more reliable than backoff.
    sems = {
        "anthropic_chair": asyncio.Semaphore(5),
        "cerebras_reasoning": asyncio.Semaphore(1),
        "moonshot_longctx": asyncio.Semaphore(3),
        "groq_velocity": asyncio.Semaphore(1),
    }

    results = {}
    async with httpx.AsyncClient() as client:
        async def guarded(slug, rid):
            async with sems[rid]:
                return await run_one(client, slug, alumni_md[slug], common, rid)

        coros = [guarded(slug, rid) for slug, rid in jobs]
        for coro in asyncio.as_completed(coros):
            slug, rid, wrapped, err = await coro
            if err:
                print(f"  !  {slug:25s} {rid:22s} ERR: {err[:120]}")
                results[(slug, rid)] = ("error", err)
                continue
            out_path = OUT_DIR / f"{slug}__{rid}.json"
            out_path.write_text(json.dumps(wrapped, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            score = wrapped.get("overall_score", 0)
            verdict = wrapped.get("verdict", "?")
            print(f"  +  {slug:25s} {rid:22s} score={score:.2f} {verdict}")
            results[(slug, rid)] = ("ok", wrapped)

    # Summary table per alumnus
    print()
    print("==> Summary (overall_score per reviewer)")
    print(f"  {'alumnus':<22s} {'anth':>6s} {'cere':>6s} {'moon':>6s} {'groq':>6s}  avg")
    print("  " + "-" * 60)
    for slug in ALUMNI:
        scores = {}
        for rid in REVIEWERS:
            status, payload = results.get((slug, rid), (None, None))
            if status == "ok":
                scores[rid] = float(payload.get("overall_score", 0))
        if not scores:
            print(f"  {slug:<22s} NO REVIEWS")
            continue
        avg = sum(scores.values()) / len(scores)
        anth = scores.get("anthropic_chair", float("nan"))
        cere = scores.get("cerebras_reasoning", float("nan"))
        moon = scores.get("moonshot_longctx", float("nan"))
        groq = scores.get("groq_velocity", float("nan"))
        def fmt(x): return f"{x:6.2f}" if x == x else "  ----"
        print(f"  {slug:<22s} {fmt(anth)} {fmt(cere)} {fmt(moon)} {fmt(groq)}  {avg:.2f}")

    ok_count = sum(1 for v in results.values() if v[0] == "ok")
    err_count = len(results) - ok_count
    print()
    print(f"==> {ok_count}/{len(jobs)} reviews succeeded ({err_count} errors)")
    print(f"==> Output: {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
