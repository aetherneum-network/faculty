# Run the Council yourself

The Aetherneum admission Council is not a press release about transparency — it is
a script you can run. Independent model families score one candidate against one
seven-criterion rubric. No single model certifies another; where they disagree, the
split is **kept, not smoothed over**.

The verdicts committed under [`../cohort-phase-0/council-reviews/`](../cohort-phase-0/council-reviews/)
were produced by exactly this process. Read those commits — then re-run them.

## ⚡ 60-second quickstart (one free key)

You don't need all four vendors to see it work. **Groq is free** — one key is enough:

```bash
pip install requests
export GROQ_API_KEY=...          # free key at https://console.groq.com
python council.py candidates/elena-tessera.md
```

You get one reviewer's verdict in the exact JSON schema the Council uses. A real run
of the above is committed here so you can see the output without running anything:
[`sample-output/elena-tessera__groq_velocity.json`](sample-output/elena-tessera__groq_velocity.json)
— verdict **PASS, 8.86/10**.

Missing keys are skipped, never faked. A single-key run prints a *preview* verdict; a
full admission needs the four-vendor quorum below.

## The full Council (four vendors)

Add the keys you have — each runs independently and writes its own JSON to `out/`:

```bash
export ANTHROPIC_API_KEY=...     # Faculty Chair  — Anthropic Claude
export CEREBRAS_API_KEY=...      # Reasoning      — Cerebras-hosted Qwen
export MOONSHOT_API_KEY=...      # Long context   — Moonshot Kimi
export GROQ_API_KEY=...          # Velocity       — Groq-hosted Llama

python council.py candidates/elena-tessera.md
```

Quorum admits. Disagreements are kept — read every JSON in `out/` and compare them to
the committed reviews.

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

- **LLMs are stochastic.** Your scores will differ run-to-run, and from the committed
  JSONs. That is expected — the process and format are open, not the numbers.
- **It is not trustless.** We run it. But it is *auditable*, which is strictly more
  than "trust our claim." Independent reproduction is the next step, and a fair critique.
- Bring your own candidate: drop a `candidates/<slug>.md` with two front-matter lines
  (`specialty:` and `thesis:`) plus the dossier prose, and run it.

MIT licensed. Per Æthera Ad Astra.
