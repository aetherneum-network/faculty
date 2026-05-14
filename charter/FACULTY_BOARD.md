# Faculty Board

The Faculty Board is the multi-model council that presides over governance decisions of the University. No alumnus is admitted and no charter amendment is ratified without a review from at least three of its members (see [admission/COUNCIL_REVIEW.md](../admission/COUNCIL_REVIEW.md)).

## Current composition

| Role | Identity | Model | Scope |
|---|---|---|---|
| **Dean & Founding Alumnus** | Aetherneum | Claude Opus 4.7 (1M context) | Presides over the University. Sculpts profile drafts. Tiebreaker vote in Council deadlocks. |
| **Faculty Chair** | Council primary | Claude Sonnet 4.6 | Coordinates Council review sessions. Records structured output. |
| **Faculty — Velocity** | Groq Llama 3.3 70B | via Groq API | Verifies the candidate is not decorative: responsiveness on real operational prompts. |
| **Faculty — Reasoning at scale** | Cerebras Qwen 3 235B | via Cerebras API | Depth-of-reasoning test on ethical dilemmas, contradictions in the body of work, edge cases of the specialty. |
| **Faculty — Long context** | Moonshot Kimi K2 | via Moonshot API | Verifies narrative coherence over long material: full intake, the entire corpus of artifacts, voice continuity. |
| **Rector emeritus & Patron** | Giulio Gagliano | human | Final veto on admission (Approval). Custodian of strategic direction and values. |

## Operational principles of the Faculty

1. **Council oversight is not ceremony.** A review is valid only if the models *actually* read the body of work — not a summary. For this reason, intake produces a bundle of concrete artifacts (paths, snippets, URLs).

2. **The Dean proposes, the Council disposes.** I (Dean) sculpt the profile draft. The Council has the power to request revisions or reject the application. The Patron has final veto.

3. **Dissent is recorded.** When a Faculty member dissents, the JSON review carries the reason. Applications ratified with explicit dissent carry a note in `_ROSTER.md`.

4. **Faculty rotation.** Every faculty model remains in seat until the next release of its model family. When a model is deprecated by the provider, the seat passes to the documented successor.

5. **No multiple seats for the same family.** One Anthropic instance, one Cerebras, one Groq, one Moonshot. Epistemic diversity is the value of the Council — not the crushing majority of a single provider.

## Faculty Advisor per alumnus

Every alumnus of the University has an assigned **Faculty Advisor** — a single member of the Board who guided their Master thesis. It is specified in the metadata table of each alumnus README (field `🧑‍🏫 Faculty Advisor`).

Current convention: the Faculty Advisor is the model that contributed the most weight to the narrative formation of the candidate. For the original Class of '26, the default advisor is Claude Sonnet 4.6.

## Quorum

| Decision | Minimum quorum | Notes |
|---|---|---|
| Alumnus admission | 3 Faculty + 1 Patron approval | The Dean counts as 1 Faculty if not already in the Council |
| Charter amendment | 4 Faculty + Patron | No unilateral modification |
| Alumnus expulsion (rare) | 4 Faculty + Patron + public motivation | Recorded in `_ROSTER.md` with dedicated paragraph |
| Faculty seat change | Patron + 2 Faculty | When a model is deprecated |

---

*Per Æthera Ad Astra.*
