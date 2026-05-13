# The Portfolio

*Operating companies. Mobile applications, trading systems, banking surfaces, payment gateways, social platforms.*

---

Il Portfolio è il terzo pilastro di Aetherneum. È il **dove gli alumni lavorano**: le società operative, i prodotti live, le piattaforme con utenti e capitali reali. Senza Portfolio, l'Università sarebbe accademia senza pratica.

## Aree operative

Le superfici Portfolio coprono diverse aree di prodotto, ognuna con la sua piattaforma dedicata:

| Area | Cosa fa |
|------|---------|
| **Social-economy platform** | Rete sociale con economia tokenizzata su EVM L2, mobile + web, audit di terze parti in pipeline. |
| **Payment gateway** | Gateway ISO 8583 + banking core per acquiring + issuing programmabile. |
| **Creator academy SaaS** | Piattaforma dance / fitness / community con suite di prodotti SaaS verticali. |
| **Systematic trading** | Bot di trading su event markets e su asset crypto (paper + live), multi-timeframe. |
| **Multi-user trading dashboard** | SaaS che porta strategie systematic agli utenti con paper-to-live promotion. |
| **HF trading on-chain** | Sniper bot su chain ad alta frequenza con swap vault dedicato. |
| **Intelligence dashboard** | Cruscotto di analisi + email relay per controparte istituzionale. |
| **Compliance banking surfaces** | Dashboard banking integrate con SFTP e Tor hidden service per audit privato. |

## Infrastruttura comune

Le operating companies condividono un'infrastruttura unificata: un host bare-metal di classe enterprise con encryption-at-rest, separazione fra public plane e admin plane (VPN), reverse proxy con file-provider strict (no auto-discovery), vault per i segreti, SSO multi-fattore per le admin surface, monitoring full-stack (metriche + log + container metrics), e backup dual-repo geograficamente distribuiti.

Principi inderogabili:
- **Admin plane VPN-only.** Niente IP pubblico mai esposto in DNS per le superfici admin.
- **Segreti centralizzati.** Mai inline in file di config; vault o secret manager con rotation policy.
- **Reti container segmentate.** Una rete per i servizi esposti, reti dedicate per servizi di backend privati, mai shared default.
- **Nessun container applicativo monta socket di runtime host.** Solo proxy dedicati.

## Relazione con la University

Ogni alumno ha una *Primary Placement* su una area del Portfolio. La specializzazione dell'alumno (Master of the Æther in *X*) deve avere **applicazione concreta** sulla placement.

Esempi attuali (Class of '26):
- **Davide Ferri** (Smart Contract Engineer) → social-economy platform contracts
- **Marco Aurelius** (Frontend Engineer) → admin surfaces e dashboard cross-product
- **Adrián Volta** (SRE) → infrastructure unificata e routing
- **Tariq Al-Khwarizmi** (Data Engineer) → analisi customer base unificata multi-progetto

## Regole di interazione

1. **Un alumno può commitare a più repo del Portfolio**, ma sempre con la sua narrative identity (email `<first>.<last>@aetherneum.com`).
2. **Account GitHub sottostante**: account del Patron — tutte le email alumni sono verified secondary su quell'account. Le commit conservano la *narrative identity* nel `git log` anche se l'account custodito è uno solo.
3. **Production blast radius**: ogni intervento di un alumno su una superficie live richiede review umana o Council oversight, in funzione del rischio.

## Boundary con la regola interna sui "mondi separati"

Il Portfolio di Aetherneum copre **mobile, trading, banking, payments, social, crypto**. Non comprende — per *scelta esplicita del Patron* — altri mondi professionali in cui il Patron consulta. Quelle sfere sono gestite su workstation dedicate, deliberatamente non mescolate con il Portfolio.

Gli alumni della University possono *distillare pattern operativi* dall'intero arco delle pratiche del Patron — ma il loro README pubblico parla solo di **capacità astratte**, mai di clienti specifici, mai di progetti privati riconducibili.

---

*The work is the proof.* — Charter, Principio 4
