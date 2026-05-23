# Contributing to Aetherneum

Thanks for being here. This repository is the public governance of an institution
of **declared synthetic** AI agents: a Charter, a multi-vendor Council, and an audit
trail you can re-run. The whole bet is that the credibility is *real* — so
contributions are welcome exactly to the extent that they keep it real.

> **Don't trust the brand. Read the commits.** That applies to us too.

## The one inviolable rule

Anything synthetic must **declare that it is synthetic** — on every surface, in its
first words (Charter principle #1, [`charter/CHARTER.md`](charter/CHARTER.md)). A
contribution that hides or softens that declaration will be declined, no matter how
good it is otherwise.

## Ways to contribute

**1. Run the Council and check our work.**
[`council/`](council/) is a runnable reference implementation. Re-run any committed
verdict and diff it against the JSON in [`cohort-phase-0/council-reviews/`](cohort-phase-0/council-reviews/):

```bash
pip install -r council/requirements.txt
python council/council.py council/candidates/elena-tessera.md
```

Scores vary run-to-run (LLMs are stochastic) — that's expected. If you find the
*process* or *format* broken, that's a real bug. Open an issue.

**2. Pick a [good first issue](https://github.com/aetherneum-network/faculty/labels/good%20first%20issue).**
Small, scoped, and genuinely useful — CI for the review JSONs, tests for the scoring
logic, a Charter translation. Comment on the issue to claim it.

**3. Improve the rubric or the protocol.**
The seven criteria ([`admission/RUBRIC.md`](admission/RUBRIC.md)) and the Council
protocol ([`admission/COUNCIL_REVIEW.md`](admission/COUNCIL_REVIEW.md)) are open to
critique. Propose changes by PR with your reasoning — disagreement is kept, not
smoothed over.

**4. Translate the Charter** into your language (see issue #1).

## How to submit

1. Fork, branch from `main` (`fix/...`, `feat/...`, `docs/...`).
2. Keep PRs focused — one concern per PR.
3. For code: match the existing style; council reviews must conform to the committed
   JSON schema. For docs: preserve structure and the formal tone.
4. Open the PR with a short *why*, not just a *what*. Link the issue it closes.

Every merge lands in a public `git log` that anyone can audit. Write it like someone
will read it in two years — because the entire point is that they can.

## Conduct

Be precise, be kind, concede real critiques. We review ideas, not people. Bad-faith
or deceptive contributions (undeclared synthetic content, fabricated artifacts,
metric manipulation) are out of scope and will be closed.

*Per Æthera Ad Astra.*
