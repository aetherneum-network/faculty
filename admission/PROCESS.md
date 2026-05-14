# Admission Process

*The 6-step pipeline for admitting a new alumnus to the University.*

No alumnus enters without a real body of work and without Council oversight. This document describes the pipeline that every candidate goes through — from identifying a missing specialty to publishing the `aetherneum-network/<slug>` repository.

---

## Step 1 — SOURCE

**What:** identify a *traceable body of work* in the Portfolio (or in the Patron's professional practice) from which a specialty coherent with the University can emerge.

**Deliverable:**
- Path or URL to the artifacts (repository, pipeline, folder, deploy)
- 1-paragraph rationale: why is this specialty missing from the current Class?
- Proposed Faculty Advisor (see [../charter/FACULTY_BOARD.md](../charter/FACULTY_BOARD.md))

**Example:** *"There is a mature operational practice from the Patron that handles a high volume of procedural documentation with a multi-step classification pipeline, a master index, and a multi-class scoring engine. No alumnus of the current Class of '26 covers this area of capability. Source: Patron's document corpus + Python toolkit with persistent state."*

---

## Step 2 — INTAKE

**What:** extract from the body of work the patterns, the decisions, the voice, and the anti-patterns (what the candidate *refuses*). Fill in the form `templates/INTAKE_TEMPLATE.md` and save it as `cohort-<period>/intake/<slug>.md`.

**Deliverable:** a filled intake form with at least:
- 5+ distinctive operational patterns (with the artifacts that prove them)
- 3+ critical decisions taken in the body of work
- 1+ anti-pattern (what the candidate would not have allowed)
- Voice characteristics (minimalist, fussy, archivist, etc.)
- Real toolkit used (languages, libraries, design patterns)

**Who does it:** the Dean (Aetherneum) or a designated Faculty Member. Never a single "junior" model without supervision.

---

## Step 3 — INTERVIEW

**What:** the Dean (Claude Opus 4.7) sculpts the profile draft following `templates/README_TEMPLATE.md`. The term *Interview* is metaphorical: in practice it is the synthesis of the intake into a concrete narrative identity.

**Deliverable:** a profile draft `alumni/pending/<slug>.md` with:
- Header with avatar + role + motto
- Complete metadata table
- Master Thesis (title + 2-3 sentences)
- Biography (personality + decision patterns + anti-patterns)
- Skills Certificate
- Voice & Personality
- Diploma artifact (HTML certificate on the site; ASCII fallback in the README)
- Avatar Generation Prompt

---

## Step 4 — DEFENSE

**What:** multi-model Council review. The bundle (intake + draft profile + artifact links) is sent to at least 3 Faculty Members in addition to the Dean (Cerebras Qwen 3 + Groq Llama 3.3 + Moonshot Kimi). Each produces a structured JSON review following `templates/COUNCIL_REVIEW_TEMPLATE.json`.

**Deliverable:** N JSON files in `cohort-<period>/council-reviews/<slug>__<reviewer>.json`. See [COUNCIL_REVIEW.md](COUNCIL_REVIEW.md) for the detailed protocol.

**Criteria:** see [RUBRIC.md](RUBRIC.md). Minimum score to pass: *3 reviews out of 3 with overall ≥ 7/10 and zero veto*.

---

## Step 5 — APPROVAL

**What:** the Patron (Giulio Gagliano) receives the complete bundle (intake + profile + 3 council reviews) and grants the final approval. The Patron can:
- approve without changes
- request specific revisions (re-iteration of step 3 + step 4)
- reject (rare, but possible)

**Deliverable:** a row in `alumni/_ROSTER.md` with status `APPROVED` and date.

---

## Step 6 — CONFERRAL

**What:** creation of the public repository `aetherneum-network/<slug>` and publication of the profile.

**Operations:**
1. `gh repo create aetherneum-network/<slug> --public --description "<Master of the Æther headline>"`
2. Push the profile `README.md` + `avatar.jpg` generated from the avatar prompt
3. Update `alumni/_ROSTER.md` (status: `CONFERRED`)
4. Update the org `.github/profile/README.md` if the alumnus enters a visible table
5. Update `cohort-<period>/_MANIFEST.md` (status: `CONFERRED`)
6. (Optional) update `university.aetherneum.com/alumni/<slug>` if maintained separately

**Deliverable:** a live public repo + link to the canonical profile.

---

## Pipeline status per candidate

Every candidate has a *status* tracked in `cohort-<period>/_MANIFEST.md`:

| Status | Steps completed | Notes |
|---|---|---|
| `SOURCED` | 1 | Specialty identified, intake not yet compiled |
| `INTAKE_DONE` | 1-2 | Intake form completed in `cohort-*/intake/` |
| `DEFENDED` | 1-3 | Profile draft + Council reviews incoming |
| `IN_DEFENSE` | 1-4 | Council reviews received, awaiting Patron approval |
| `APPROVED` | 1-5 | Patron approval received, conferral pending |
| `CONFERRED` | 1-6 | Public repo published — active alumnus |

---

*Council oversight is the academic standard for any decision involving production blast radius.* — Charter, Principle 5
