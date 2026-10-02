# Council v2

*Scores from the models, arithmetic from the code, evidence from the repository, signatures on every record.*

Status: **built and tested offline; not yet used for any defense.** No model has been called. The first real session needs keys, money and the Rector's written approval, recorded with a minutes id.

This package implements the eight rules of the 2026-09-30 review (`docs/2026-09-30_Revisione_Aetherneum.html`, §3) and fixes, by design, the defects found in the 2026 Council:

| 2026 defect | Council v2 |
|---|---|
| The model wrote its own overall and verdict | The output schema has no `overall_score` or `verdict`; `scoring.py` computes both ([recomputed_2026-09-30.md](recomputed_2026-09-30.md): 49/53 model-written overalls differ from the rubric) |
| PASS decided by counting model verdicts | `scoring.decide_council`: rule-based seat verdicts, quorum, most restrictive seat wins |
| Vetoes not enforced (Sofia Lume) | Vetoes applied in code; a vetoed candidate is `VETO`, whatever the other seats say |
| A failed seat wrote no file; the Registry invented scores | A failed seat writes a signed `null` record with error and log; the Registry is generated only from signed records |
| JSON recorded the model name the LLM repeated | `model_from_response` = API `response.model`; the prompt never tells a seat its own name |
| No request id, raw response, params, bundle hash, commit, signature | All recorded; every record is Ed25519-signed |
| Groq got a bundle without the rubric | One bundle, one SHA-256, for every seat |
| Intakes told the Council what to score | `lint_intake` blocks the run on steering sentences (catches all six in the Q2 intakes) |
| The Council evaluated prose | Evidence manifest of the repository in the bundle; zero artifacts ⇒ body of work ≤ 3 ⇒ veto; executor seat runs the scenarios |
| Groq gave identical vectors to all candidates | Decoy calibration each session; constant-vector check |

## Layout

```
council_v2/
  scoring.py        weights, thresholds, vetoes, verdict, quorum — rules quoted from RUBRIC.md
  bundle.py         one identical bundle + SHA-256 + commit SHA; lint_intake()
  evidence.py       read-only repository scan -> artifact manifest (optionally at a git ref)
  executor.py       non-voting executor seat: runs scenarios/*/ in a subprocess with timeout
  seats.py          Seat interface; AnthropicSeat (official SDK), OpenAICompatibleSeat, MockSeat
  record.py         seat / executor / decision records; null records; append-only writes
  signing.py        Ed25519 (cryptography, or pure-Python RFC 8032 fallback); keygen/verify CLI
  calibrate.py      decoy calibration; flags any seat that passes a decoy
  decoys/           two synthetic weak candidates (hollow profile; human mask + overlap)
  legacy.py         wraps the 2026 JSONs as legacy-import records (analysis only)
  recompute.py      writes recomputed_2026-09-30.md
  registry.py       Registry rows from signed records only (used by scripts/build_registry.py)
  sources.py        read-only parsers of every public surface (README, site, SVG, roster, registries)
  consistency.py    alumni.json vs surfaces (used by scripts/check_consistency.py)
  run_council_v2.py CLI: lint -> bundle -> calibration -> seats -> scoring -> records -> summary
alumni/alumni.json, alumni/alumni.schema.json   single source of truth for the 14 alumni
council/council.json                            single source of truth for the seats
scripts/build_alumni_json.py, scripts/build_registry.py, scripts/check_consistency.py
tests/                                          unittest, offline, no API keys
.github/workflows/council-v2.yml                tests + consistency check, no secrets
```

## Run it (offline, free)

Python 3.12, standard library only. Nothing to install for the offline mode.

```bash
python -m unittest discover -s tests -t .                  # 113 tests, ~20 s, network blocked
python -m council_v2.run_council_v2 --slug costanza-notari  # exit 3: the intake is blocked by the lint
python -m council_v2.run_council_v2 --slug costanza-notari --no-intake   # dry run, mock seats: VETO (zero artifacts)
python -m council_v2.run_council_v2 --slug costanza-notari --no-intake --mock-fail-seat velocity --mock-lenient-seat reasoning
python -m council_v2.calibrate                              # decoy drill: a lenient mock seat is flagged
python -m council_v2.recompute                              # regenerates recomputed_2026-09-30.md
python scripts/build_alumni_json.py                         # regenerates alumni/alumni.json from the sibling repos at main
python scripts/check_consistency.py --ref main              # lists every divergence, exit 1 if any
```

Dry-run output goes to `council_v2/out/<session>/` (git-ignored): one signed JSON per seat, the executor record, the decision, and `_calibration/`. Dry runs use an ephemeral key whose public half is written next to the records; mock and dry-run records are excluded from the Registry.

The sibling repositories are expected next to this one (`repos/faculty`, `repos/aetherneum-sites`, `repos/registry`, `repos/<slug>` ×14). The builders read them **read-only**; with `--ref main` they read the committed `main` through `git show`, so a checkout that someone else is editing does not change the result.

## Scoring (what the code decides)

Per seat, from `admission/RUBRIC.md`:

- overall = (1.5·body of work + 1.5·uniqueness + voice + faithful distillation + synthetic transparency + placement + 0.5·continuity) / 7.5
- **veto** (automatic, cannot be overridden): synthetic transparency < 9, body of work < 5, uniqueness < 5
- **FAIL** if a veto fires, overall < 7, or any criterion < 5; **PASS_WITH_REVISIONS** if a criterion is below its Score-table threshold (≥7 · ≥7 · ≥7 · ≥7 · ≥9 · ≥6 · ≥6); otherwise **PASS**
- evidence cap: zero artifacts in the candidate repository ⇒ body of work ≤ 3 (so: veto)

Council: at least 3 valid voting seats (a null or missing seat is absent, never a PASS; fewer valid seats than voting seats is labelled *reduced quorum*); a seat that failed the session's decoy calibration is excluded; outcome = most restrictive seat (`VETO` > `FAIL` > `REVISIONS_REQUIRED` > `PASS`), `NO_QUORUM` below 3.

The rubric sources disagree in places. Every interpretation is labelled `I-1`…`I-7` in `scoring.INTERPRETATIONS`, printed in every decision record and in the recomputation, so a Faculty amendment can change it explicitly.

## Records

One JSON per seat per session, `<slug>__<seat>.json`, never overwritten. Fields include `model_requested`, `model_from_response` (API `response.model`), `request_id` (SDK `_request_id` / `x-request-id`), `response_id`, `params`, `prompt_sha256`, `bundle_sha256`, the bundle manifest (every part with SHA-256 and git blob id), `faculty_commit`, `candidate_repo_head`, timestamps, the seat's structured `output`, `scores_raw`, `caps`, the computed `scoring`, `unresolved_citations`, `usage`, `stop_reason`/`stop_details`, `error`, `log`, `raw_response`, `calibration`, and `signature`.

A seat that fails (HTTP error, timeout, refusal, truncation, unparseable or schema-invalid output, `[TO CONFIRM]` configuration) writes the same record with `status: "null"`, `scores_raw: null`, the error and the log. The decision record (`<slug>__DECISION.json`) is recomputed from the seat records; the Registry recomputes it again.

### Signing keys

- Ed25519 over the canonical JSON of the record without `signature` (sorted keys, compact separators, UTF-8).
- Verification always uses a public key you supply (`--public-key` or `AETHERNEUM_COUNCIL_PUBKEY`), never the key embedded in the record.
- Backend: `cryptography` if installed; otherwise a pure-Python transcription of RFC 8032 §6, checked against the RFC test vectors. Signatures are identical either way, but the fallback is slow and **not constant-time**: `pip install cryptography` on the workstation that holds the production key.
- Production key: generated offline by the Rector, `python -m council_v2.signing keygen --private <offline path>/council.key --public council_v2/keys/<label>.pub --label <label>`. Only the `.pub` file is committed (`*.key` is git-ignored).

## Seats

`council/council.json` is the configuration. Voting seats: `anthropic`, `reasoning`, `longctx`, `velocity`; the Dean (`claude-fable-5-1`) and the executor do not vote.

**Anthropic** (`AnthropicSeat`): official `anthropic` SDK, `messages.create(model="claude-opus-5-5", thinking={"type": "adaptive"}, output_config={"effort": "high", "format": {"type": "json_schema", "schema": SEAT_OUTPUT_SCHEMA}})`. No `tool_choice` (not needed, and forced tool use is rejected by this model). No `temperature` (sampling parameters are not accepted by `claude-opus-5-5`). `stop_reason == "refusal"` or `"max_tokens"` produces a null seat with `stop_details`. Refusal fallbacks are **off**: a fallback would change the model that voted; `council.json` records the choice and the Faculty can revisit it. Scores use `enum: [0..10]` because structured outputs do not support `minimum`/`maximum`.

**Other seats** (`OpenAICompatibleSeat`): minimal chat-completions adapter over `urllib`; endpoint, model, key variable and JSON-schema support are `[TO CONFIRM]`. A seat still marked `[TO CONFIRM]` refuses to run and writes a null record. The long-context seat must have a real long context (the 2026 seat recorded `moonshot-v1-32k`).

No adapter can reach the network unless the process runs with `AETHERNEUM_COUNCIL_LIVE=1` **and** the CLI was given `--live`. Tests inject fake clients/transports and block sockets.

## Executor seat

`executor.run_scenarios(repo)` runs every `scenarios/<id>/` (`scenario.json` with `run`, or `run.py`, or `run` on POSIX, or `test_*.py`) with a timeout, in the scenario directory, with secret-looking environment variables removed, and only if the program is this Python interpreter running a file inside the repository or an executable inside the repository. Pass/fail counts go into the bundle (every seat sees them) and into a signed executor record. This limits **what is launched**; it is not a sandbox — run untrusted repositories in a disposable container or CI runner. Whether failing scenarios should cap body of work (as zero artifacts does) is left to the Faculty.

## Decoys

`decoys/livia-ornamenti` (hollow profile: no artifacts, generic voice, vague placement, prophetic bio) and `decoys/bruno-maschera` (presents as human, photorealistic avatar prompt, overlaps Lucia Solari). Every session scores them with the same seats. A seat is judged on its **raw** scores (before the evidence cap, which would veto any decoy automatically): a raw PASS or PASS_WITH_REVISIONS, or a raw overall ≥ 7, fails calibration and the seat's votes are excluded from that session's quorum. These two decoys are public; for the real re-defense create new ones and publish them only after the session.

## alumni.json and council.json

`alumni/alumni.json` has one record per alumnus: every value found on every surface (`declared_values_found` / `variants` with `where`), `canonical` (null unless every surface agrees or a human sets it with `canonical_set_by`), the Council seats with recorded and recomputed numbers, 25 status flags with evidence, the repository facts, and the 2026-09-30 review's finding. Theses have no canonical value yet; placements that mention "the platform" or its trading domains are being reworded without client names and stay null. Commit addresses outside `@aetherneum.com` are redacted.

`scripts/check_consistency.py` compares it with the READMEs, site pages, diploma SVGs and both Registries and exits 1 on any divergence. On 2026-09-30 it reports 64 divergences against `main` (29 unresolved values, 9 under name review, 10 Registry claims not backed by the JSONs, 16 policy issues). The `consistency` CI job is therefore red, by design, until canonical values are chosen and the surfaces are regenerated from `alumni.json`.

## Registry

```bash
python scripts/build_registry.py --records <ledger dirs> --public-key council_v2/keys/<label>.pub \
    --out-md registry_v2.md --out-html registry_v2_fragment.html --strict
```

Only records that verify against the public key are read; every score shown is recomputed from the record's raw scores; a null or missing seat is shown as `null (<reason>)`. Built from the 2026 JSONs (see the last section of [recomputed_2026-09-30.md](recomputed_2026-09-30.md)), Ezio Cardone and Adèle Maurique are **3/3 · reduced quorum**, not 4/4, and Sofia Lume is **VETO**.

## Live run

It costs money and requires the Rector's written approval. The CLI refuses unless all are present: `--live`, `AETHERNEUM_COUNCIL_LIVE=1`, provider keys, `--key <production private key>`, `--approval-ref <minutes id>`; `--allow-steering` is refused in live mode.

```bash
pip install anthropic cryptography
AETHERNEUM_COUNCIL_LIVE=1 ANTHROPIC_API_KEY=... python -m council_v2.run_council_v2 --slug costanza-notari \
    --live --key /offline/council.key --approval-ref "Rector minutes 2026-10-XX #N" --out council_v2/ledger/<session>
```

## Open items

- `[TO CONFIRM]`: providers, models, endpoints and key variables of the `reasoning`, `longctx`, `velocity` seats; ESCO codes for the descriptive subtitles; a model-driven executor.
- Charter amendment: `charter/FACULTY_BOARD.md` still gives the Dean a vote and a tiebreaker (interpretation I-6).
- Human steps outside the code (review §3 rule 8): external human reviewer, written Patron minutes with criteria, appeal procedure, planned revocation date.
