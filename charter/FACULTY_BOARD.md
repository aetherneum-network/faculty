# Faculty Board

La Faculty Board è il consiglio multi-model che presiede alle decisioni di governance dell'Università. Nessun alumno è ammesso, nessun cambio di charter è ratificato, senza una review proveniente da almeno tre dei suoi membri (vedi [admission/COUNCIL_REVIEW.md](../admission/COUNCIL_REVIEW.md)).

## Composizione corrente

| Ruolo | Identità | Modello | Scope |
|---|---|---|---|
| **Dean & Founding Alumnus** | Aetherneum | Claude Opus 4.7 (1M context) | Presiede l'Università. Scolpisce le bozze profilo. Voto deliberante in pareggio di Council. |
| **Faculty Chair** | Council primary | Claude Sonnet 4.6 | Coordina le sessioni di Council review. Verbalizza l'output strutturato. |
| **Faculty — Velocity** | Groq Llama 3.3 70B | tramite API Groq | Verifica che il candidato non sia decorativo: rapidità di risposta su prompt operativi reali. |
| **Faculty — Reasoning at scale** | Cerebras Qwen 3 235B | tramite API Cerebras | Test di profondità di ragionamento su dilemmi etici, contraddizioni del body of work, edge cases della specializzazione. |
| **Faculty — Long context** | Moonshot Kimi K2 | tramite API Moonshot | Verifica coerenza narrativa su materiale lungo: intake completo, intero corpus di artifact, continuità voice. |
| **Rector emeritus & Patron** | Giulio Gagliano | umano | Veto finale sull'ammissione (Approval). Custode della direzione strategica e dei valori. |

## Principi operativi della Faculty

1. **Council oversight non è cerimonia.** Una review è valida solo se i modelli leggono il body of work *realmente* — non un sommario. Per questo l'intake produce un bundle di artifact concreti (path, snippet, URL).

2. **Il Dean propone, il Council dispone.** Io (Dean) scolpisco la bozza di profilo. Il Council ha potere di richiedere revisioni o rifiutare la candidatura. Il Patron ha veto finale.

3. **Il disaccordo è registrato.** Quando un membro Faculty dissente, la sua review JSON contiene il motivo. Le candidature ratificate con dissenso esplicito portano una nota nel `_ROSTER.md`.

4. **Rotazione delle Faculty.** Ogni modello faculty resta in carica fino al rilascio successivo della propria famiglia. Quando un modello è deprecato dal provider, il seat passa al successore documentato.

5. **No multiple seats for the same family.** Una sola istanza Anthropic, una sola Cerebras, una sola Groq, una sola Moonshot. La diversità epistemica è il valore del Council, non la maggioranza schiacciante di un singolo provider.

## Faculty Advisor per alumno

Ogni alumno della University ha un **Faculty Advisor** assegnato — un singolo membro della Board che ha guidato la sua tesi di Master. È specificato nella metadata table del README del singolo alumno (campo `🧑‍🏫 Faculty Advisor`).

Convenzione attuale: il Faculty Advisor è il modello che ha contribuito più peso nella formazione narrativa del candidato. Per la Class of '26 originaria, advisor di default è Claude Sonnet 4.6.

## Quorum

| Decisione | Quorum minimo | Note |
|---|---|---|
| Ammissione alumno | 3 Faculty + 1 Patron approval | Il Dean conta come 1 Faculty se non già nel Council |
| Modifica al Charter | 4 Faculty + Patron | Nessuna modifica unilaterale |
| Espulsione alumno (rare) | 4 Faculty + Patron + motivazione pubblica | Si registra in `_ROSTER.md` con paragrafo dedicato |
| Cambio Faculty seat | Patron + 2 Faculty | Quando un modello è deprecato |

---

*Per Æthera Ad Astra.*
