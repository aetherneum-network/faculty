# How to read a Council Review

Council Review files are public JSON records of Step 4, the Defense phase of the Aetherneum admission process. They let an outside reader see which model reviewed a candidate, what evidence it used, how it scored the seven rubric criteria, and whether the candidate can proceed.

Example used below: [`cohort-q2-2026/council-reviews/costanza-notari__anthropic_chair.json`](../cohort-q2-2026/council-reviews/costanza-notari__anthropic_chair.json).

## File name

Council Reviews follow this pattern:

```text
<candidate-slug>__<reviewer-id>.json
```

For example, `costanza-notari__anthropic_chair.json` means the candidate is Costanza Notari and the review was written by the Anthropic Faculty Chair reviewer.

## Header fields

The first fields identify the reviewer and the candidate:

- `reviewer_name`: the Council role, such as `Faculty Chair`, `Velocity`, `Reasoning at scale`, or `Long context`.
- `reviewer_model`: the exact model that produced the review.
- `reviewer_provider`: the model provider, such as `anthropic`, `groq`, `cerebras`, or `moonshot`.
- `review_date`: the ISO timestamp when the review was produced.
- `candidate_slug`: the candidate identifier, such as `costanza-notari`.
- `candidate_specialty`: the proposed Master of the Aether specialty.
- `candidate_master_thesis`: the thesis title distilled from the candidate's body of work.

In the example, the Faculty Chair reviewed Costanza Notari for the specialty `Procedural Vigilance` and recorded the exact model and timestamp that produced the evaluation.

## Criterion scores

The `criterion_scores` object contains seven criteria. Each criterion has:

- `score`: an integer from 0 to 10.
- `rationale`: a short explanation grounded in the candidate's intake, profile draft, or artifacts.

The seven criteria are:

1. `body_of_work_depth`: whether the candidate has a real, traceable, verifiable body of work.
2. `specialty_uniqueness`: whether the specialty fills a real gap in the current Class.
3. `voice_personality_clarity`: whether the candidate has a recognizable voice and clear refusals.
4. `faithful_distillation`: whether the profile faithfully reflects actual work instead of exaggerating.
5. `synthetic_transparency`: whether the profile clearly declares the candidate's synthetic nature.
6. `placement_fit`: whether the proposed placement has enough operational material to justify the alumnus.
7. `continuity_with_class`: whether name, motto, prose, and avatar prompt fit the existing Class voice.

In the example, Costanza receives `synthetic_transparency: 10` because the profile explicitly declares her synthetic status and includes visible synthetic markers. She receives `placement_fit: 8` because the reviewer accepts the cross-portfolio specialty while noting it is less company-specific than some other placements.

## Overall score

`overall_score` is the normalized weighted score. The rubric gives extra weight to:

- `body_of_work_depth`: 1.5x
- `specialty_uniqueness`: 1.5x
- `continuity_with_class`: 0.5x

The example score is `9.36`, which signals a very strong pass. The `notes` field explains why: the candidate has a mature body of work, a gap-filling specialty, and no veto triggers.

## Verdict

`verdict` is one of:

- `PASS`: the candidate can proceed if Council quorum agrees.
- `PASS_WITH_REVISIONS`: the candidate is promising but must revise specific points.
- `FAIL`: the reviewer found a blocking issue.

`revisions_required` lists required changes when the verdict is `PASS_WITH_REVISIONS`. For a clean `PASS`, it is usually an empty array.

`dissent` is `null` when the reviewer does not dissent. If a reviewer disagrees with the expected majority, this field records why.

## Veto rules

Some failures override the overall score. A reviewer can mark `FAIL` when any of these are true:

- `synthetic_transparency < 9`: synthetic identity is non-negotiable.
- `body_of_work_depth < 5`: the candidate lacks enough proof of capability.
- `specialty_uniqueness < 5`: the specialty critically overlaps an existing alumnus.

The example explicitly says no veto applies because Costanza has `synthetic_transparency: 10`, `body_of_work_depth: 9`, and `specialty_uniqueness: 10`.

## Reading a review in two minutes

1. Check `candidate_slug`, `candidate_specialty`, and `candidate_master_thesis` to understand who and what is being evaluated.
2. Read the seven `criterion_scores` and scan for any score below the threshold.
3. Check `overall_score` and `verdict`.
4. If the verdict is not a clean `PASS`, read `revisions_required` or `dissent`.
5. Read `notes` for the reviewer's final qualitative judgment.

The Council Review is not just a scorecard. It is a public audit trail showing the evidence, the reviewer, the model, the criteria, and the decision path.
