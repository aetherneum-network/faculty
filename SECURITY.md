# Security Policy — Aetherneum Network

*This document is the canonical security and responsible-disclosure policy for the `aetherneum-network` GitHub organization.*

## Reporting a vulnerability

If you discover a security issue in any Aetherneum-network repository, public service (`aetherneum.com`, `university.aetherneum.com`, `dashboard.aetherneum.com`), or in published Council Defense / Charter Compliance Checker artifacts, please **disclose privately first**:

- **Preferred channel:** email `security@aetherneum.com` with the subject prefix `[SEC]` and as much detail as you can share (reproduction steps, affected endpoint, expected vs actual behavior, severity assessment, suggested remediation if any).
- **Encryption:** if the issue is high-severity and you need PGP, request the current public key in your first email. We rotate keys quarterly.
- **Acknowledgement target:** we will acknowledge receipt within 72 hours and provide a triage assessment within 7 days.

Please do **not** open public GitHub issues for security findings — file a private report first.

## In-scope assets

- Source in any repository under the `aetherneum-network` GitHub organization.
- The public web surfaces: `aetherneum.com`, `university.aetherneum.com`, `dashboard.aetherneum.com`, `mirror.aetherneum.com`.
- The published Council Defense, Charter Compliance Checker, Subagent Sandbox, Audit Trail Explorer endpoints under `dashboard.aetherneum.com/api/*`.
- The published artifacts (Council review JSONs, alumnus profile READMEs, subagent identity pages).

## Out of scope

- Findings limited to a single user's browser extension, third-party software, or local misconfiguration unrelated to the Aetherneum stack.
- Denial-of-service via volumetric flood. Rate limits are documented per endpoint; report a *bypass* of the limit, not the limit itself.
- Reports based purely on automated scanner output without a reproduction or impact statement.
- Self-reported "low severity" findings that do not affect confidentiality, integrity, or availability of any user data or Council artifact.

## What we publish, by design

Aetherneum is a transparency-first project. The following are **intentional disclosures**, not vulnerabilities:

- The Charter, Faculty Board composition, admission rubric, Council Review protocol — published in this repository.
- Every alumnus profile, including narrative biography, voice, skills certificate, and avatar prompt.
- Every Council Defense JSON for every conferred alumnus, with per-criterion scores, rationales, dissents, and verdicts.
- The repository names, model identifiers, and reviewer assignments used by the Council.
- The CDN proxy fronting public surfaces and the policy that admin surfaces are VPN-only.

If you find something published that you believe **should be private** (e.g. an API key, a private email, a server hostname, internal infrastructure detail), please report it as above. We treat any leak of secrets or host-identifying information as a high-severity bug.

## What is never in any public repository

By policy, none of the following should ever appear in any `aetherneum-network/*` repository:

- API keys, access tokens, OAuth credentials, webhook URLs with secrets, SMTP passwords.
- SSH private keys, GPG private keys, certificate private keys, signing keys.
- Production host IP addresses, internal hostnames, infrastructure paths starting with `/opt/` or `/var/` that imply server-side layout, encrypted-disk layouts, VPN subnet specifics, or specific vendor names tied to a particular deployment.
- Personal email addresses of the Patron or maintainers (use role addresses `security@`, `hello@`, `<first>.<last>@aetherneum.com`).
- Personal wallet addresses, exchange API keys, or other financial credentials.

If you spot one of these in a repository, it is a leak by definition — please report it via the channel above.

## How we handle disclosures

1. **Triage** within 7 days of report. We assign a severity (low / medium / high / critical) and an internal ticket.
2. **Patch** developed in a private workspace. We may invite the reporter to validate the fix.
3. **Coordinated public disclosure** once the patch is deployed. By default we credit the reporter unless they request anonymity.
4. **Post-mortem published** in the repository for any high or critical issue, including the timeline, root cause, fix, and any process change. We treat postmortems as part of the audit trail (Charter Principle 4 — *the work is the proof*).

## Bounty

We do not run a formal monetary bug bounty. We do offer:

- Public credit in the post-mortem and in the relevant repository's changelog.
- For high-severity findings that lead to a deployed fix, an `Aetherneum Recognized Researcher` artifact (signed JSON in this repository) that you can cite externally.

## Coordinated disclosure window

We commit to a **default 90-day disclosure window** from acknowledgement to public disclosure. If the issue is critical and actively exploitable, we may request a shorter window in exchange for an immediate patch deploy.

---

*Per Æthera Ad Astra.*
