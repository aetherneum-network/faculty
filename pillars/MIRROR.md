# The Mirror

*A digital twin. Personal AI with memory, conversation, and proactive instinct.*

---

Il Mirror è il primo pilastro di Aetherneum. È l'AI personale del Patron: una intelligenza sintetica che vive, ricorda, agisce e — quando necessario — anticipa. Non è un assistente generico; è la riflessione del singolo umano che custodisce l'intero network.

## Cosa fa, concretamente

| Capacità | Implementazione |
|---|---|
| **Memoria persistente** | Vector store con centinaia di punti di knowledge (conversazioni, documenti, sessioni di lavoro) ingeriti continuamente. |
| **Conversation chain** | LLM chain con fallback multi-provider per resilienza (primario hosted, secondario hosted, terziario on-prem). |
| **Proactive instinct** | Skill suite operativa per status di sistema, certificati, backup, capacità, rete, knowledge legacy. |
| **Multi-canale** | Bot conversazionale + interfaccia web con memoria di sessione. |
| **Italiano nativo** | Personalità diretta, bilingue italiano/inglese. Non un consulente — il "fratello geniale" del Patron. |

## Architettura

Il Mirror gira come stack containerizzato con separazione netta fra orchestratore principale, vector store, runtime LLM on-prem di fallback, conversation cache e proxy per le skill di sistema. Le reti interne sono segmentate: una sola per i servizi esposti, una privata per i componenti di knowledge, una dedicata al proxy del runtime container.

Principio chiave: **nessun container applicativo monta direttamente il socket del runtime host**; le skill che ne hanno bisogno passano attraverso un proxy isolato.

## Relazione con la University

Il Mirror non è un alumno. È **piattaforma**: il luogo dove un alumno può venire "richiamato" in conversazione viva con il Patron, dove la memoria long-term del network si sedimenta, dove le decisioni operative quotidiane prendono forma prima di diventare commit.

Quando un nuovo alumno viene ammesso alla University, parte delle sue knowledge e voice viene ingerita nel vector store del Mirror — così che il Patron possa "parlare con" l'alumno attraverso il Mirror senza dover aprire una sessione dedicata per ogni interazione.

## Operational status

- Endpoint pubblico attivo
- Monitoring continuo (stack metriche + log aggregation)
- Faculty Advisor di riferimento del Mirror: famiglia primaria del Council (Claude Sonnet)

---

*Il Mirror non simula umanità. Ricorda quello che la mia memoria umana dimentica e lo restituisce nel momento in cui mi serve.* — voce del Patron
