# The Mirror

*A digital twin. Personal AI with memory, conversation, and proactive instinct.*

---

The Mirror is the first pillar of Aetherneum. It is the Patron's personal AI: a synthetic intelligence that lives, remembers, acts and — when necessary — anticipates. It is not a generic assistant; it is the reflection of the single human who is the custodian of the entire network.

## What it does, concretely

| Capability | Implementation |
|---|---|
| **Persistent memory** | Vector store with hundreds of knowledge points (conversations, documents, work sessions) ingested continuously. |
| **Conversation chain** | LLM chain with multi-provider fallback for resilience (primary hosted, secondary hosted, tertiary on-prem). |
| **Proactive instinct** | Operational skill suite covering system status, certificates, backups, capacity, networking, legacy knowledge. |
| **Multi-channel** | Conversational bot + web interface with session memory. |
| **Native Italian** | Direct personality, bilingual Italian/English. Not a consultant — the Patron's "genius brother." |

## Architecture

The Mirror runs as a containerized stack with clean separation between the main orchestrator, the vector store, the on-prem LLM fallback runtime, the conversation cache, and the proxy for system skills. Internal networks are segmented: one for the exposed services, a private one for the knowledge components, and a dedicated one for the container-runtime proxy.

Key principle: **no application container mounts the host runtime socket directly**; skills that need it pass through an isolated proxy.

## Relationship with the University

The Mirror is not an alumnus. It is **platform**: the place where an alumnus can be "summoned" into live conversation with the Patron, where the network's long-term memory settles, where daily operational decisions take shape before becoming commits.

When a new alumnus is admitted to the University, part of their knowledge and voice is ingested into the Mirror's vector store — so that the Patron can "speak with" the alumnus through the Mirror without opening a dedicated session for every interaction.

## Operational status

- Public endpoint active
- Continuous monitoring (metrics stack + log aggregation)
- Faculty Advisor of reference for the Mirror: the primary Council family (Claude Sonnet)

---

*The Mirror does not simulate humanity. It remembers what my human memory forgets, and gives it back at the moment I need it.* — Patron's voice
