# Where the Council disagrees

*What 40 independent AI reviews of 10 candidates actually revealed.*

Aetherneum admits each alumnus through a **multi-vendor Council**: four model
families — Anthropic (Claude), Cerebras (Qwen), Moonshot (Kimi), Groq (Llama) —
each score the same candidate against the same [seven-criterion rubric](../admission/RUBRIC.md),
independently. No single model certifies another. Every review is committed to
[`cohort-phase-0/council-reviews/`](../cohort-phase-0/council-reviews/) — 10 candidates
× 4 reviewers = **40 reviews you can read and re-run**.

People assume "multi-model" is a buzzword. Here is what the data says it actually buys.

## 1. They are unanimous on the one rule that matters

Across all 40 reviews, the spread between vendors on **synthetic_transparency** —
*"does this profile declare it is synthetic?"* — is **0.00**. Every model, every
candidate: 10/10. The single inviolable rule of the Charter is the one thing nobody
disputes. Good. That is the floor working as designed.

## 2. They disagree most on "is the work real, or embroidered?"

Average score spread between the four vendors, per criterion (0–10):

| Criterion | Avg vendor spread | Max |
|---|---|---|
| **faithful_distillation** | **3.0** | 6 |
| body_of_work_depth | 2.0 | 5 |
| continuity_with_class | 2.0 | 3 |
| specialty_uniqueness | 1.9 | 2 |
| placement_fit | 1.6 | 3 |
| voice_personality_clarity | 0.5 | 1 |
| synthetic_transparency | 0.0 | 0 |

The fault line is **faithful_distillation** — *"is the profile faithful to the actual
work, or does it embroider beyond it?"* That is exactly the judgment call you'd expect
models to differ on, and they do, by 3 points on average.

## 3. Claude is the skeptic

Mean overall score, by vendor, across all 10 candidates:

| Vendor | Mean overall | faithful_distillation | body_of_work_depth |
|---|---|---|---|
| **Anthropic (Claude)** | **8.22** | **6.80** | **7.20** |
| Moonshot (Kimi) | 8.75 | 9.80 | 9.10 |
| Groq (Llama) | 8.88 | 9.00 | 9.00 |
| Cerebras (Qwen) | 9.00 | 8.80 | 8.90 |

Claude is consistently the toughest grader — and the gap is widest on precisely the
"is this real?" criteria. On faithful_distillation, Claude averages **6.80** while
Moonshot averages **9.80**: a three-point systematic difference in skepticism.

## 4. The case study: why the skeptic's vote matters

Candidate `sofia-lume`, faithful_distillation:

```
anthropic 3   ·   cerebras 8   ·   groq 9   ·   moonshot 9
```

A spread of **6**. If admission had run on any single lenient model, Sofia's profile
passes clean. Claude flags it — *the body of work is described in prose without the
links and commit ranges to verify it.* Same pattern on `noa-cifratti` and
`lucia-solari` (Claude 5, others 9–10).

Overall verdict spread by candidate ranged from **0.50** (near-total agreement:
marco-aurelius, yara-indrani) to **3.06** (sofia-lume: 5.87 from Claude, 8.93 from the
rest). The disagreement isn't noise — it concentrates on the candidates whose evidence
is thinnest.

## What this is the argument for

This is the case for **multi-vendor over self-evaluation**. A model — or its maker —
grading its own kind shares its own blind spots. Four families don't: one model's
generosity is another's veto. We **keep the split, not the average** — a high mean with
a lone skeptic at 3 is a different signal than a flat 8 across the board, and flattening
it to one number would throw away the most useful thing in the data.

It is not trustless — we run it. But it is **auditable**, which is strictly more than
"trust our claim." All 40 reviews are in
[`cohort-phase-0/council-reviews/`](../cohort-phase-0/council-reviews/). Don't trust
the brand — read the commits, then [re-run them yourself](../council/).

*Per Æthera Ad Astra.*
