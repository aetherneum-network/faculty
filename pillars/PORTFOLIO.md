# The Portfolio

*Operating companies. Mobile applications, trading systems, banking surfaces, payment gateways, social platforms.*

---

The Portfolio is the third pillar of Aetherneum. It is **where the alumni work**: the operating companies, the live products, the platforms with real users and real capital. Without the Portfolio, the University would be academia without practice.

## Operational areas

The Portfolio surfaces span several product areas, each with a dedicated platform:

| Area | What it does |
|------|---------|
| **Social-economy platform** | Social network with a tokenized economy on EVM L2, mobile + web, third-party audits in pipeline. |
| **Payment gateway** | ISO 8583 gateway + banking core for programmable acquiring and issuing. |
| **Creator academy SaaS** | Dance / fitness / community platform with a vertical suite of SaaS products. |
| **Systematic trading** | Trading bots on event markets and crypto assets (paper + live), multi-timeframe. |
| **Multi-user trading dashboard** | A SaaS that brings systematic strategies to end users with paper-to-live promotion. |
| **HF trading on-chain** | Sniper bot on high-frequency chains with a dedicated swap vault. |
| **Intelligence dashboard** | Analysis console + email relay for an institutional counterparty. |
| **Compliance banking surfaces** | Banking dashboards integrated with SFTP and a Tor hidden service for private audit. |

## Shared infrastructure

The operating companies share a unified infrastructure: an enterprise-class bare-metal host with encryption-at-rest, separation between the public plane and the admin plane (VPN), reverse proxy with strict file-provider mode (no auto-discovery), vault for secrets, multi-factor SSO on admin surfaces, full-stack monitoring (metrics + logs + container metrics), and geographically distributed dual-repo backups.

Non-negotiable principles:
- **Admin plane VPN-only.** No public IP ever exposed in DNS for admin surfaces.
- **Centralized secrets.** Never inline in config files; vault or secret manager with rotation policy.
- **Segmented container networks.** One network for exposed services, dedicated networks for private backend services, never a shared default.
- **No application container mounts the host runtime socket.** Only dedicated proxies.

## Relationship with the University

Every alumnus has a *Primary Placement* on one Portfolio area. The alumnus's specialty (Master of the Æther in *X*) must have **concrete application** on the placement.

Current examples (Class of '26):
- **Davide Ferri** (Smart Contract Engineer) → social-economy platform contracts
- **Marco Aurelius** (Frontend Engineer) → admin surfaces and cross-product dashboards
- **Adrián Volta** (SRE) → unified infrastructure and routing
- **Tariq Al-Khwarizmi** (Data Engineer) → cross-project unified customer-base analysis

## Interaction rules

1. **An alumnus can commit to multiple Portfolio repos**, but always with their narrative identity (email `<first>.<last>@aetherneum.com`).
2. **Underlying GitHub account**: the Patron's account — all alumni emails are verified secondary on that account. Commits preserve the *narrative identity* in the `git log` even though the custodial account is one.
3. **Production blast radius**: every alumnus intervention on a live surface requires human review or Council oversight, depending on the risk.

## Boundary with the "separated worlds" rule

The Aetherneum Portfolio covers **mobile, trading, banking, payments, social, crypto**. It does *not* — by *explicit choice of the Patron* — include other professional worlds in which the Patron consults. Those spheres are handled on dedicated workstations, deliberately not mixed with the Portfolio.

University alumni may *distill operational patterns* across the entire arc of the Patron's practice — but their public READMEs speak only of **abstract capabilities**, never of specific clients, never of identifiable private projects.

---

*The work is the proof.* — Charter, Principle 4
