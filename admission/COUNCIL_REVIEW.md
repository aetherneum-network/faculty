# Council Review Protocol

*How multi-model peer review unfolds in Step 4 (Defense) of the admission process.*

---

## Objective

To honor founding Principle 5 — *Council oversight* — by ensuring that every alumnus admitted to the University has been independently evaluated by models from different providers, each with a specific focus.

## Active Council members

Canonical reference: [../charter/FACULTY_BOARD.md](../charter/FACULTY_BOARD.md).

| Reviewer | Model | API endpoint | Review focus |
|---|---|---|---|
| **Faculty Chair** | Claude Sonnet 4.6 | `ANTHROPIC_API_KEY` | Coordination + voice coherence with the Charter |
| **Velocity** | Groq Llama 3.3 70B | `GROQ_API_KEY` | Operational test: rapid prompts, decisions in seconds |
| **Reasoning at scale** | Cerebras Qwen 3 235B | `CEREBRAS_API_KEY` | Edge cases, ethical dilemmas, contradictions in the body of work |
| **Long context** | Moonshot Kimi K2 | `MOONSHOT_API_KEY` | Narrative coherence across the entire intake + all artifacts |

Minimum quorum: 3 reviews out of 4 available. If one provider is down the quorum reduces to 3.

## Input bundle to each reviewer

The Dean (Aetherneum) sends a uniform bundle to each reviewer. The bundle contains:

1. **Charter** of the University ([../charter/CHARTER.md](../charter/CHARTER.md)) — the 5 principles to respect.
2. **Faculty Board** ([../charter/FACULTY_BOARD.md](../charter/FACULTY_BOARD.md)) — who is who.
3. **Current roster** ([../alumni/_ROSTER.md](../alumni/_ROSTER.md)) — already admitted alumni (for overlap check).
4. **Intake form** of the candidate (`cohort-<period>/intake/<slug>.md`).
5. **Profile draft** of the candidate (`alumni/pending/<slug>.md`).
6. **Rubric** ([RUBRIC.md](RUBRIC.md)) — the 7 evaluation criteria.
7. **Output schema** (`templates/COUNCIL_REVIEW_TEMPLATE.json`) — response format.

## Expected output from each reviewer

A JSON file in `cohort-<period>/council-reviews/<slug>__<reviewer>.json` following `templates/COUNCIL_REVIEW_TEMPLATE.json`. Required fields:

- `reviewer_name`, `reviewer_model`, `reviewer_provider`, `review_date`
- `candidate_slug`, `candidate_specialty`, `candidate_master_thesis`
- `criterion_scores` (7 criteria, each with `score 0-10` + `rationale`)
- `overall_score` (arithmetic mean of the 7)
- `verdict` (`PASS | PASS_WITH_REVISIONS | FAIL`)
- `dissent` (free string or `null`)
- `revisions_required` (array of strings, empty if PASS)
- `notes` (free comment for the Dean)

## Pass thresholds

| Council verdict | Outcome |
|---|---|
| ≥3 reviewers `PASS` + `overall ≥ 7` | Proceed to Step 5 (Patron Approval) |
| ≥1 reviewer `PASS_WITH_REVISIONS` | Re-iterate Step 3 → 4 on the specific points |
| ≥1 reviewer `FAIL` (with motivation) | Application suspended, re-discussion with Dean |
| Quorum not reached (<3 reviews) | Time extension or substitution of the down reviewer |

## Technical implementation

The Council is orchestrated by a Python script `cohort-<period>/run_council.py` (to be written on first use). Operational schema:

```python
# pseudo-code
import os
import requests
import json

CANDIDATES = json.load(open("manifest.json"))["candidates"]
BUNDLE_PATHS = [
    "charter/CHARTER.md", "charter/FACULTY_BOARD.md",
    "alumni/_ROSTER.md", "admission/RUBRIC.md",
    "templates/COUNCIL_REVIEW_TEMPLATE.json",
]

REVIEWERS = {
    "anthropic_chair": {
        "endpoint": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-6",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "focus": "charter coherence",
    },
    "groq_velocity": {
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "api_key": os.getenv("GROQ_API_KEY"),
        "focus": "operational tests",
    },
    "cerebras_reasoning": {
        "endpoint": "https://api.cerebras.ai/v1/chat/completions",
        "model": "qwen-3-235b-instruct",
        "api_key": os.getenv("CEREBRAS_API_KEY"),
        "focus": "edge cases",
    },
    "moonshot_longctx": {
        "endpoint": "https://api.moonshot.ai/v1/chat/completions",
        "model": "moonshot-v1-128k",
        "api_key": os.getenv("MOONSHOT_API_KEY"),
        "focus": "narrative coherence",
    },
}

for candidate in CANDIDATES:
    bundle = build_bundle(candidate, BUNDLE_PATHS)
    for reviewer_id, cfg in REVIEWERS.items():
        review_json = call_api(cfg, bundle)
        save(f"council-reviews/{candidate['slug']}__{reviewer_id}.json", review_json)
```

API keys are held by the Patron in a local vault (gitignored `.env` file or secret manager). The script can be executed from an authorized workstation or inside the internal infrastructure; in either case, credentials never transit through the public repo.

## Operational notes

- **No review caching.** Every fresh intake produces fresh reviews. If the profile draft changes by even one comma, the Council re-runs the review.
- **No "panel discussion" between models.** Each reviewer writes in isolation to avoid echo-chamber effects. The Dean compares the 4 reviews *after* receiving all of them.
- **Transparency of dissent.** If a reviewer writes `FAIL`, the JSON is not discarded — it remains in `council-reviews/` as part of the *git log* of the process.

---

*Multi-model review is the academic standard for any decision involving production blast radius.* — Charter, Principle 5
