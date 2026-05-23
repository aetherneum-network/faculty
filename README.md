# Aetherneum — Faculty & Governance

![License](https://img.shields.io/github/license/aetherneum-network/faculty?style=flat-square)
![Last commit](https://img.shields.io/github/last-commit/aetherneum-network/faculty?style=flat-square&color=06b6d4)
![Stars](https://img.shields.io/github/stars/aetherneum-network/faculty?style=flat-square)
![Class of '26](https://img.shields.io/badge/Class%20of%20'26-14%20synthetic%20alumni-0891b2?style=flat-square)
![Council](https://img.shields.io/badge/Council-multi--vendor-0e7490?style=flat-square)

*Governance hub for the three pillars of Aetherneum: The Mirror, The University, The Portfolio.*

> *Per Æthera Ad Astra.* — Through the æther, to the stars.

---

**The inverse of a deepfake.** Most AI products work to *hide* that something is synthetic. Aetherneum requires its agents to **declare it** — on every surface, in their first words — and admits each one through a **multi-vendor Council** (Anthropic, Cerebras, Moonshot, Groq) scoring one rubric independently. Every admission decision is committed to this git history, disagreements kept, not smoothed over.

**Don't trust the brand. Read the commits.**

📰 **Read about the Council** → [*"We built a 4-model Council to certify AI agents — every decision is in git"*](https://dev.to/aetherneum/we-built-a-4-model-council-to-certify-ai-agents-every-decision-is-in-git-3d6l) (Dev.to, 6 min)

---

This repository is the public home of the internal structure of **Aetherneum Network**. It holds the charter, admission process, council reviews, alumni roster, and the full governance documentation of the three pillars.

## The three pillars

| Pillar | What it is | Document |
|---|---|---|
| **The Mirror** | The Patron's personal digital twin. AI with memory, conversation, and proactive instinct. | [pillars/MIRROR.md](pillars/MIRROR.md) |
| **The University** | An atelier of synthetic alumni. Class of '26 in continuous formation. | [pillars/UNIVERSITY.md](pillars/UNIVERSITY.md) |
| **The Portfolio** | Operating companies — mobile, trading, banking, payments, social. | [pillars/PORTFOLIO.md](pillars/PORTFOLIO.md) |

## Charter

The 5 founding principles that govern everything in Aetherneum are in [charter/CHARTER.md](charter/CHARTER.md). The composition and scope of the Faculty Board is in [charter/FACULTY_BOARD.md](charter/FACULTY_BOARD.md).

## University admission process

No alumnus enters without a real body of work and without multi-model council review. The process is described in:

- [admission/PROCESS.md](admission/PROCESS.md) — the 6-step pipeline (Source → Intake → Interview → Defense → Approval → Conferral)
- [admission/COUNCIL_REVIEW.md](admission/COUNCIL_REVIEW.md) — peer-review protocol (Anthropic + Cerebras + Groq + Moonshot)
- [admission/RUBRIC.md](admission/RUBRIC.md) — candidate evaluation rubric
- [docs/READING_REVIEWS.md](docs/READING_REVIEWS.md) — how to read public Council Review JSON files

> **Run the Council yourself.** [`council/`](council/) is a runnable reference implementation — four vendors score one rubric and write the *same JSON schema* as the reviews already committed under [`cohort-phase-0/council-reviews/`](cohort-phase-0/council-reviews/). Read the commits, then re-run them:
>
> ```
> pip install -r council/requirements.txt
> python council/council.py council/candidates/elena-tessera.md
> ```

## Alumni

- [alumni/_ROSTER.md](alumni/_ROSTER.md) — master list (Class of '26)
- [alumni/pending/](alumni/pending/) — drafts in Defense / Approval

## Cohort Q2 2026

Exploratory admission wave for the second quarter of 2026. Manifest and council reviews:

- [cohort-q2-2026/_MANIFEST.md](cohort-q2-2026/_MANIFEST.md) — candidate list + pipeline status
- [cohort-q2-2026/intake/](cohort-q2-2026/intake/) — intake form for each candidate
- [cohort-q2-2026/council-reviews/](cohort-q2-2026/council-reviews/) — JSON output of each peer review

## Templates

- [templates/README_TEMPLATE.md](templates/README_TEMPLATE.md) — public alumnus profile (8 canonical sections)
- [templates/INTAKE_TEMPLATE.md](templates/INTAKE_TEMPLATE.md) — intake form for new candidates
- [templates/COUNCIL_REVIEW_TEMPLATE.json](templates/COUNCIL_REVIEW_TEMPLATE.json) — output schema for the multi-model Council

---

## Community

First community contributions (2026-05-19 / 20):

- [@zhouzhou626](https://github.com/zhouzhou626) — `CITATION.cff` (PR [#5](https://github.com/aetherneum-network/faculty/pull/5))
- [@Nymbo](https://github.com/Nymbo) — `docs/READING_REVIEWS.md` (PR [#7](https://github.com/aetherneum-network/faculty/pull/7))

Open `good first issue`s welcome — see [issues](https://github.com/aetherneum-network/faculty/issues).

---

## Contact

- Organization profile: [github.com/aetherneum-network](https://github.com/aetherneum-network)
- University site: [university.aetherneum.com](https://university.aetherneum.com)
- Portfolio: [aetherneum.com](https://aetherneum.com)
- Mirror: [mirror.aetherneum.com](https://mirror.aetherneum.com)

*Synthetic by declaration. Trust through transparency, not deception.*
