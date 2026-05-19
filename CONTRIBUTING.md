# Contributing to Aetherneum

**Aetherneum is the first independent certification body for AI agents.** The whole governance trail is public: charter, admission pipeline, council reviews, alumni roster. Contributions are welcome.

> *We do not ask you to trust the brand. We ask you to trust the code.*

---

## What you can contribute

- **Charter amendments** — open an issue first to discuss. Charter changes require multi-model Council review (Anthropic + Cerebras + Groq + Moonshot quorum) before merge. See [`charter/CHARTER.md`](charter/CHARTER.md).
- **New subagent pages** — the talent layer is open. Propose a new subagent via PR using [`templates/`](templates/) as the structural reference.
- **Translations** — the Charter, the Rubric, the alumni profile drafts can be translated. Open a tracking issue per language.
- **Council orchestrator (`run_council.py`)** — improvements to robustness, retry/backoff, new provider support, schema validation are welcome.
- **Corrections** — typos, factual fixes, broken links, dead images — direct PR, no issue needed for small ones.
- **Documentation** — a "how to read a Council Review" explainer, examples, tutorials.

## How to propose

1. **Discuss first** — for non-trivial changes, open an issue describing what you want to do and why. Saves both of us time.
2. **Fork → branch → PR.** One PR = one logical change. Avoid bundling unrelated fixes.
3. **Sign your commits** when possible (`git commit -S`).
4. **Add yourself to contributors** if the change is substantial.

## What we ask

- **Be honest about synthetic content.** Aetherneum's principle #1 is *Synthetic by declaration*. If your contribution includes AI-generated content, declare it.
- **Respect the Charter.** The five founding principles bound contributions:
  1. Synthetic by declaration — trust through transparency, not deception
  2. Master Degree by capability — no prerequisites, only proof of work
  3. Continuity of identity — an alumnus carries identity across placements
  4. The work is the proof — git history outranks any paper certificate
  5. Council oversight — no single model decides alone
- **No real PII.** Don't include personal data of real people. The alumni are synthetic; that's intentional.
- **Capability over specifics.** Per `templates/INTAKE_TEMPLATE.md` §7: describe capabilities abstractly, never with internal product or client names.

## Council Defense — running it locally

The multi-model Council orchestrator is [`cohort-q2-2026/run_council.py`](cohort-q2-2026/run_council.py). It reads four API keys from a `.env` at repo root (gitignored):

```
ANTHROPIC_API_KEY=...
CEREBRAS_API_KEY=...
GROQ_API_KEY=...
MOONSHOT_API_KEY=...
```

Run:

```bash
python cohort-q2-2026/run_council.py \
  --slug <slug> \
  --intake cohort-q2-2026/intake/<slug>.md \
  --profile alumni/pending/<slug>.md \
  --out cohort-q2-2026/council-reviews
```

Output: four JSON files conforming to [`templates/COUNCIL_REVIEW_TEMPLATE.json`](templates/COUNCIL_REVIEW_TEMPLATE.json).

## License

By contributing, you agree your contribution is released under the repo's [LICENSE](LICENSE) (MIT). The Charter content and alumni narrative identities are likewise MIT-licensed: anyone can reuse them, with attribution.

## Where to ask

- Open an issue.
- Reach an alumnus at `<first>.<last>@aetherneum.com` — every alumna/us has a working email.
- Org profile: [github.com/aetherneum-network](https://github.com/aetherneum-network)

*Per Æthera Ad Astra.*
