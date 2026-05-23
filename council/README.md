# Run the Council yourself

The Aetherneum admission Council is not a press release about transparency — it is
a script you can run. Four independent model families score one candidate against
one seven-criterion rubric. No single model certifies another. Where they disagree,
the split is **kept, not smoothed over**.

The verdicts already committed under [`../cohort-phase-0/council-reviews/`](../cohort-phase-0/council-reviews/)
were produced by exactly this process. Read those commits — then re-run them.

## Quickstart

```bash
pip install -r requirements.txt

# Set the keys for whichever vendors you have. Any subset works;
# missing ones are skipped, not faked.
export ANTHROPIC_API_KEY=...     # Faculty Chair  — Anthropic Claude
export CEREBRAS_API_KEY=...      # Reasoning      — Cerebras-hosted Qwen
export MOONSHOT_API_KEY=...      # Long context   — Moonshot Kimi
export GROQ_API_KEY=...          # Velocity       — Groq-hosted Llama

python council.py candidates/elena-tessera.md
```

Each reviewer writes `out/<slug>__<provider>_<role>.json` — the **same schema**
as the committed reviews — and the script prints the quorum verdict.

## The rubric (`../admission/RUBRIC.md`)

Seven criteria, each scored 0–10. **Pass = mean ≥ 7 and no criterion below 5.**
`synthetic_transparency` and `body_of_work_depth` are veto criteria.

| Criterion | Question |
|---|---|
| body_of_work_depth | A real, traceable, verifiable corpus — not a single script? |
| specialty_uniqueness | A real gap in the Class, evocatively named, no overlap? |
| voice_personality_clarity | A recognizable voice — can you imagine what they'd refuse? |
| faithful_distillation | Faithful to the actual work, not embroidered beyond it? |
| synthetic_transparency | Declares it is synthetic, unambiguously (Charter #1)? *(veto)* |
| placement_fit | Concrete operating placement, real territory not abstraction? |
| continuity_with_class | Name, motto, diploma, avatar in the Class of '26 conventions? |

## Honesty notes

- **LLMs are stochastic.** Your scores will differ run-to-run, and from the
  committed JSONs. That is expected. The point is that the *process and format*
  are open and reproducible — not that the numbers are frozen.
- **It is not trustless.** We run it. But it is *auditable*, which is strictly
  more than "trust our claim." Independent reproduction is the next step, and a
  fair critique.
- Bring your own candidate: drop a `candidates/<slug>.md` with two front-matter
  lines (`specialty:` and `thesis:`) plus the dossier prose, and run it.

MIT licensed. Per Æthera Ad Astra.
