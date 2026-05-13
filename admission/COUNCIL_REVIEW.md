# Council Review Protocol

*Come si svolge la peer review multi-model nello Step 4 (Defense) del processo di ammissione.*

---

## Obiettivo

Onorare il Principio fondativo 5 — *Council oversight* — assicurando che ogni alumno ammesso alla University abbia ricevuto valutazione indipendente da modelli di provider diversi, ognuno con un focus specifico.

## Membri attivi del Council

Riferimento canonico: [../charter/FACULTY_BOARD.md](../charter/FACULTY_BOARD.md).

| Reviewer | Modello | API endpoint | Focus della review |
|---|---|---|---|
| **Faculty Chair** | Claude Sonnet 4.6 | `ANTHROPIC_API_KEY` | Coordinamento + voce coerenza con Charter |
| **Velocity** | Groq Llama 3.3 70B | `GROQ_API_KEY` | Test operativo: prompt rapidi, decisioni in pochi secondi |
| **Reasoning at scale** | Cerebras Qwen 3 235B | `CEREBRAS_API_KEY` | Edge cases, dilemmi etici, contraddizioni nel body of work |
| **Long context** | Moonshot Kimi K2 | `MOONSHOT_API_KEY` | Coerenza narrativa su intero intake + tutti gli artifact |

Quorum minimo: 3 review su 4 disponibili. Se uno provider è down il quorum si riduce a 3.

## Input per ogni reviewer

Il Dean (Aetherneum) invia ad ogni reviewer un bundle uniforme. Il bundle contiene:

1. **Charter** dell'Università ([../charter/CHARTER.md](../charter/CHARTER.md)) — i 5 principi da rispettare.
2. **Faculty Board** ([../charter/FACULTY_BOARD.md](../charter/FACULTY_BOARD.md)) — chi è chi.
3. **Roster corrente** ([../alumni/_ROSTER.md](../alumni/_ROSTER.md)) — alumni già ammessi (per check di sovrapposizione).
4. **Intake form** del candidato (`cohort-<period>/intake/<slug>.md`).
5. **Bozza profilo** del candidato (`alumni/pending/<slug>.md`).
6. **Rubric** ([RUBRIC.md](RUBRIC.md)) — i 7 criteri di valutazione.
7. **Output schema** (`templates/COUNCIL_REVIEW_TEMPLATE.json`) — formato della risposta.

## Output atteso da ogni reviewer

Un file JSON in `cohort-<period>/council-reviews/<slug>__<reviewer>.json` che segue `templates/COUNCIL_REVIEW_TEMPLATE.json`. Campi obbligatori:

- `reviewer_name`, `reviewer_model`, `reviewer_provider`, `review_date`
- `candidate_slug`, `candidate_specialty`, `candidate_master_thesis`
- `criterion_scores` (7 criteri, ognuno con `score 0-10` + `rationale`)
- `overall_score` (media aritmetica dei 7)
- `verdict` (`PASS | PASS_WITH_REVISIONS | FAIL`)
- `dissent` (stringa libera o `null`)
- `revisions_required` (array di stringhe, vuoto se PASS)
- `notes` (commento libero per il Dean)

## Soglie di passaggio

| Verdetto Council | Esito |
|---|---|
| ≥3 reviewer `PASS` + `overall ≥ 7` | Procede a Step 5 (Patron Approval) |
| ≥1 reviewer `PASS_WITH_REVISIONS` | Re-iterazione Step 3 → 4 sui punti specifici |
| ≥1 reviewer `FAIL` (con motivazione) | Candidatura sospesa, ridiscussione con Dean |
| Quorum non raggiunto (<3 review) | Estensione tempo o sostituzione reviewer down |

## Implementazione tecnica

Il Council è orchestrato da uno script Python in `cohort-<period>/run_council.py` (da scrivere al primo uso). Schema operativo:

```python
# pseudo-code
import os
import requests
import json

CANDIDATES = json.load(open("manifest.json"))["candidates"]
BUNDLE_PATHS = [
    "charter/CHARTER.md", "charter/FACULTY_BOARD.md",
    "alumni/_ROSTER.md", "admission/RUBRIC.md",
    "templates/COUNCIL_REVIEW_TEMPLATE.json",
]

REVIEWERS = {
    "anthropic_chair": {
        "endpoint": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-6",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "focus": "coerenza con Charter",
    },
    "groq_velocity": {
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "api_key": os.getenv("GROQ_API_KEY"),
        "focus": "test operativi",
    },
    "cerebras_reasoning": {
        "endpoint": "https://api.cerebras.ai/v1/chat/completions",
        "model": "qwen-3-235b-instruct",
        "api_key": os.getenv("CEREBRAS_API_KEY"),
        "focus": "edge cases",
    },
    "moonshot_longctx": {
        "endpoint": "https://api.moonshot.ai/v1/chat/completions",
        "model": "moonshot-v1-128k",
        "api_key": os.getenv("MOONSHOT_API_KEY"),
        "focus": "coerenza narrativa",
    },
}

for candidate in CANDIDATES:
    bundle = build_bundle(candidate, BUNDLE_PATHS)
    for reviewer_id, cfg in REVIEWERS.items():
        review_json = call_api(cfg, bundle)
        save(f"council-reviews/{candidate['slug']}__{reviewer_id}.json", review_json)
```

Le API key sono custodite dal Patron in vault locale (file `.env` gitignored o secret manager). Lo script può essere eseguito da workstation autorizzata o dentro l'infrastruttura interna; in entrambi i casi le credenziali non transitano mai nel repo public.

## Note operative

- **Niente caching delle review.** Ogni intake fresco produce review fresche. Se la bozza profilo cambia anche di una virgola, il Council rifà la review.
- **Niente "panel discussion" tra modelli.** Ogni reviewer scrive in isolamento per evitare echo chamber. Il Dean confronta le 4 review *dopo* averle ricevute tutte.
- **Trasparenza del dissenso.** Se un reviewer scrive `FAIL`, il file JSON non è cestinato — resta in `council-reviews/` come parte del *git log* del processo.

---

*Multi-model review is the academic standard for any decision involving production blast radius.* — Charter, Principio 5
