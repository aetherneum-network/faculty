# Admission Process

*Pipeline 6-step per l'ammissione di un nuovo alumno alla University.*

Nessun alumno entra senza body of work reale e senza Council oversight. Questo documento descrive la pipeline che ogni candidato attraversa — dall'identificazione di una specializzazione mancante fino alla pubblicazione del repo `aetherneum-network/<slug>`.

---

## Step 1 — SOURCE

**Cosa:** identificare un *body of work tracciabile* nel Portfolio (o nelle attività professionali del Patron) da cui possa emergere una specializzazione coerente con la University.

**Deliverable:**
- Path o URL agli artifact (repo, pipeline, cartella, deploy)
- 1-paragraph rationale: perché questa specializzazione manca alla Class corrente?
- Faculty Advisor proposto (vedi [../charter/FACULTY_BOARD.md](../charter/FACULTY_BOARD.md))

**Esempio:** *"Esiste una pratica operativa matura del Patron che gestisce alto volume di documentazione procedurale con pipeline classificatoria multi-step, indice master e scoring engine multi-classe. Nessun alumno della Class of '26 copre questa area di capacità. Source: corpus documentale del Patron + toolkit Python con state persistente."*

---

## Step 2 — INTAKE

**Cosa:** estrarre dal body of work i pattern, le decisioni, la voice, le anti-pattern (cosa il candidato *rifiuta*). Compilare il modulo `templates/INTAKE_TEMPLATE.md` salvandolo in `cohort-<period>/intake/<slug>.md`.

**Deliverable:** intake form compilato con almeno:
- 5+ pattern operativi distintivi (con artifact che li dimostrano)
- 3+ decisioni critiche prese nel body of work
- 1+ anti-pattern (cosa il candidato non avrebbe permesso)
- Tono / voice characteristics (minimalista, pignolo, archivista, ecc.)
- Toolkit reale usato (linguaggi, librerie, pattern di design)

**Chi lo fa:** il Dean (Aetherneum) o un Faculty Member designato. Mai un singolo modello "junior" senza supervisione.

---

## Step 3 — INTERVIEW

**Cosa:** il Dean (io, Claude Opus 4.7) scolpisce la bozza di profilo seguendo `templates/README_TEMPLATE.md`. Il termine *Interview* è metaforico: in pratica è la sintesi dell'intake in identità narrativa concreta.

**Deliverable:** bozza profilo `alumni/pending/<slug>.md` con:
- Header con avatar + ruolo + motto
- Metadata table completa
- Master Thesis (titolo + 2-3 frasi)
- Biography (personalità + decisione patterns + anti-patterns)
- Skills Certificate
- Voice & Personality
- Diploma ASCII art
- Avatar Generation Prompt

---

## Step 4 — DEFENSE

**Cosa:** Council multi-model review. Il bundle (intake + bozza profilo + artifact links) è inviato ad almeno 3 Faculty Members oltre al Dean (Cerebras Qwen 3 + Groq Llama 3.3 + Moonshot Kimi). Ognuno produce una review strutturata in JSON seguendo `templates/COUNCIL_REVIEW_TEMPLATE.json`.

**Deliverable:** N file JSON in `cohort-<period>/council-reviews/<slug>__<reviewer>.json`. Vedi [COUNCIL_REVIEW.md](COUNCIL_REVIEW.md) per il protocollo dettagliato.

**Criteri:** vedi [RUBRIC.md](RUBRIC.md). Score minimo per passare: *3 review su 3 con overall ≥ 7/10 e zero veto*.

---

## Step 5 — APPROVAL

**Cosa:** il Patron (Giulio Gagliano) riceve il bundle completo (intake + profile + 3 council reviews) e dà l'approval finale. Il Patron può:
- approvare senza modifiche
- richiedere revisioni specifiche (re-iterazione step 3 + step 4)
- rifiutare (raro, ma possibile)

**Deliverable:** una riga in `alumni/_ROSTER.md` con stato `APPROVED` e data.

---

## Step 6 — CONFERRAL

**Cosa:** creazione del repository public `aetherneum-network/<slug>` e pubblicazione del profilo.

**Operazioni:**
1. `gh repo create aetherneum-network/<slug> --public --description "<Master of the Æther headline>"`
2. Push del `README.md` profilo + `avatar.jpg` generato dall'avatar prompt
3. Update di `alumni/_ROSTER.md` (stato: `CONFERRED`)
4. Update del `.github/profile/README.md` org se l'alumno entra in una tabella visibile
5. Update di `cohort-<period>/_MANIFEST.md` (status: `CONFERRED`)
6. (Opzionale) update sito `university.aetherneum.com/alumni/<slug>` se gestito separatamente

**Deliverable:** repo public live + link al profilo canonico.

---

## Stato pipeline per candidato

Ogni candidato ha uno *status* attuale tracciato in `cohort-<period>/_MANIFEST.md`:

| Status | Step completati | Note |
|---|---|---|
| `SOURCED` | 1 | Specializzazione identificata, intake non ancora compilato |
| `INTAKE_DONE` | 1-2 | Intake form completato in `cohort-*/intake/` |
| `DEFENDED` | 1-3 | Bozza profilo + Council reviews in arrivo |
| `IN_DEFENSE` | 1-4 | Council reviews ricevute, attesa Patron approval |
| `APPROVED` | 1-5 | Patron approval ricevuta, conferral pending |
| `CONFERRED` | 1-6 | Repo public pubblicato — alumno attivo |

---

*Council oversight is the academic standard for any decision involving production blast radius.* — Charter, Principio 5
