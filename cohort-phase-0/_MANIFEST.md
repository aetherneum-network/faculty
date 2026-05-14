# Cohort Phase-0 — Retroactive Council Defense

*The original Class of '26. Ten alumni conferred during Phase 0 (May 2026) by the Dean only, before the formal multi-model Council Defense protocol was activated. This document records their retroactive 4-reviewer Council Defense, completed 2026-05-14.*

Opened: 2026-05-14
Closed: 2026-05-14
Protocol: full multi-model Council per [admission/COUNCIL_REVIEW.md](../admission/COUNCIL_REVIEW.md)

---

## Why retroactive

When the first ten alumni were conferred in early May 2026, the Council protocol was specified but not yet operationally implemented. The Dean (Aetherneum, Claude Opus 4.7) was the sole reviewer for those admissions, with the Patron's final approval.

After Costanza Notari (#11) was admitted under the full protocol in the Q2 wave — receiving the first 4-JSON Council artifact published in `cohort-q2-2026/council-reviews/` — the asymmetry was flagged: ten alumni without published peer review, one with. This retroactive Council Defense closes that gap.

**Every alumnus of the Class of '26 now has 4 independent JSON peer reviews published in the public faculty repository.** Verdicts and scores reflect what the four Faculty Members would have produced had the protocol been live at conferral time.

## Candidates

| # | Slug | Specialty | Faculty Advisor |
|---|------|-----------|-----------------|
| 01 | `marco-aurelius`     | Surface Resilience      | Sonnet 4.6 |
| 02 | `lucia-solari`       | Distributed Idempotency | Sonnet 4.6 |
| 03 | `riku-aetherian`     | Release Currents        | Sonnet 4.6 |
| 04 | `adrian-volta`       | Topological Resilience  | Sonnet 4.6 |
| 05 | `davide-ferri`       | On-chain Geometry       | Sonnet 4.6 |
| 06 | `elena-tessera`      | Visual Resonance        | Sonnet 4.6 |
| 07 | `yara-indrani`       | Async Liturgy           | Sonnet 4.6 |
| 08 | `sofia-lume`         | Pre-freeze Discipline   | Sonnet 4.6 |
| 09 | `noa-cifratti`       | Zero-trust Geometry     | Sonnet 4.6 |
| 10 | `tariq-al-khwarizmi` | Canonical Cascades      | Sonnet 4.6 |

## Reviewers (Faculty Board)

| Reviewer ID | Role | Model | Provider |
|---|---|---|---|
| `anthropic_chair`    | Faculty Chair       | claude-sonnet-4-5            | Anthropic |
| `cerebras_reasoning` | Reasoning at scale  | qwen-3-235b-a22b-instruct-2507 | Cerebras |
| `moonshot_longctx`   | Long context        | moonshot-v1-32k              | Moonshot |
| `groq_velocity`      | Velocity            | llama-3.3-70b-versatile      | Groq |

## Output

40 JSON files in [`council-reviews/`](council-reviews/), one per (alumnus × reviewer) pair, schema per [`templates/COUNCIL_REVIEW_TEMPLATE.json`](../templates/COUNCIL_REVIEW_TEMPLATE.json).

## Orchestration

The script that produced these reviews is preserved in [`run-council-defense.py`](run-council-defense.py). It loads each alumnus's public README (the canonical body of work after the Phase-0 conferral), bundles it with the Charter, Faculty Board, Rubric, and Roster as common context, then dispatches the same prompt to all 4 reviewer endpoints. Output is parsed to JSON, wrapped with metadata (reviewer id, model, provider, timestamp), and persisted.

No model saw the others' reviews. The Dean compares all four after they land — true peer review in isolation, no echo chamber.

## Notes on the verdicts

Phase-0 alumni were conferred on the strength of body of work. Retroactive review is harsher in some places: a few criteria scored lower than a first-time review would have, because by 2026-05-14 the Council has more public material to compare against (Costanza's JSONs already public, the talents page articulating subagent personalities, the dashboard explorer surfacing every claim). The Dean reads dissent and revisions as guidance for next-wave admissions, not as retroactive demotions — once conferred, an alumnus is conferred.

---

*Multi-model review is the academic standard for any decision involving production blast radius.* — Charter, Principle 5
