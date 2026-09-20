# AI CEO — Post-Layer-1 Strategy and Vertical-Slice Roadmap
**Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
**Created: 2026-09-18 | Maintained by: Yuvraj Gaykhe**
**Status of this document: PLANNED / PROPOSED. Nothing described here is implemented.**

> **Purpose**: This is the authoritative strategy for everything after Layer 1. It defines how
> the platform grows from the frozen connector layer toward the AI CEO vision, what the current
> data can and cannot support, and the order in which capability is built.
>
> **Companion documents**
> - `CONTEXT/AI_CEO_PROJECT_CONTEXT.md` — confirmed project state, Layer 1 record (IMPLEMENTED).
> - `CONTEXT/VS01_IMPLEMENTATION_PLAN.md` — the detailed VS-01 build plan (PLANNED).

---

## Status vocabulary

Every capability in this document carries exactly one status. Nothing may be described as
existing unless it is `IMPLEMENTED`.

| Status | Meaning |
|---|---|
| **IMPLEMENTED** | Built, tested and committed. Only Layer 1 (tasks A1–I2) holds this status. |
| **PLANNED** | Designed to implementation depth, approved in principle, not built. |
| **PROPOSED** | A design direction with open questions; must be re-grilled before build. |
| **FUTURE / CONDITIONAL** | Blocked on data, infrastructure or an external decision that does not yet exist. |

---

## 1. Strategic rationale: why vertical slices replace layer phases

### 1.1 The decision

Layer 1 was built as a horizontal phase, and that was correct: a connector and canonical
contract has no useful partial form. Everything after Layer 1 will be built as **end-to-end
vertical slices** instead. Each slice crosses the relationship model, the intelligence layer,
the reasoning layer, the decision layer and the human-approval boundary, and each slice
produces one executive-visible outcome.

### 1.2 Why

1. **A horizontal Layer 2 has no demonstrable outcome.** "The knowledge graph is finished" is
   not a result anyone can review. "The CEO is told why Meridian Textiles needs attention, with
   citations" is. With a review-driven academic calendar, every phase must end in something
   showable.
2. **Horizontal layers force premature generality.** Building "the graph" before knowing which
   queries matter guarantees building the wrong edges. Building the graph VS-01 needs, then
   extending it for VS-02, means every edge exists because a query asked for it.
3. **Layer 1's own experience is the evidence.** Layer 1 succeeded because every task had an
   acceptance criterion and a test. A horizontal Layer 2 cannot produce acceptance criteria of
   that quality, because "graph exists" is not falsifiable in a useful way.
4. **It de-risks the proposal's scope.** The proposal commits to fourteen agents, Neo4j,
   Milvus/FAISS, Redis, LangGraph/CrewAI, Temporal, n8n, XGBoost and a Temporal Fusion
   Transformer. That stack cannot be honestly delivered in the remaining time. Slices let the
   project deliver a working, defensible subset and state precisely what was descoped and why,
   rather than delivering nine half-built subsystems.
5. **Infrastructure earns its place.** A slice either needs a technology to answer its question
   or it does not. This is the only defence against a buzzword architecture.

### 1.3 The rule that follows from this

> **No infrastructure is introduced until a slice's business question cannot be answered
> without it.** Every deferred technology is recorded in §9 with the trigger condition that
> would justify introducing it.

---

## 2. What Layer 1 actually provides (IMPLEMENTED — verified 2026-09-18)

This section is ground truth, established by reading the code and data, not by reading earlier
documents. Downstream design must be built on these facts.

### 2.1 Canonical relationships that exist

`app/ingestion/reconciliation.py` defines **exactly three** canonical foreign keys:

| Relationship | Mechanism | Reliability |
|---|---|---|
| `deals.customer_id → customers.id` | Canonical FK, resolved from `customer_source_id` | Provenance-backed |
| `projects.customer_id → customers.id` | Canonical FK | Provenance-backed |
| `support_tickets.customer_id → customers.id` | Canonical FK | Provenance-backed |

### 2.2 Relationships that exist only as source-key strings

These are **not** FKs. They are `source_id` strings that must be joined inside one
`source_system`, by a consumer, at query time:

| Relationship | Carrier field |
|---|---|
| Customer → account-owner Employee | `customers.owner_source_id` |
| Deal → owner Employee | `deals.owner_source_id` |
| Project → owner Employee | `projects.owner_source_id` |
| Support ticket → assignee Employee | `support_tickets.assignee_source_id` |
| Employee → manager Employee | `employees.manager_source_id` |
| Document → owner Employee | `documents.owner_source_id` |

**Six exist; VS-01 models five.** `Project → owner Employee` is the one left out, because no VS-01
query needs a project's owner (plan §A9). The carrier field is present and the edge is a one-line
addition whenever a slice acquires a consumer for it.

### 2.3 Relationships that do not exist in any form

| Relationship | Consequence |
|---|---|
| **Document → Customer** | `DocumentCanonical` carries no customer reference at all. Any customer-document link must be **derived** by Layer 2 (see §7). |
| **Employee → Organization** | `employees.organization_id` is always `NULL`; the canonical Employee contract carries no organization source key. A known, documented B1/B2 gap. |

### 2.4 Identity and multi-source behaviour

`canonical_id = uuid5(namespace, "{source_system}:{source_entity}:{source_id}")`, and FKs
resolve **only to a parent from the same source system**. There is no cross-source entity
resolution, by design and by documented limitation.

> **Binding consequence for every slice:** all intelligence must be computed within a single
> declared `source_system` acting as system of record. Ingesting the same demo data through
> `csv_demo`, `odoo_mock` and `rest_mock` produces three independent copies of every customer.
> A slice that aggregates across source systems would triple-count. Cross-source entity
> resolution is itself a future capability (§9), not an assumption.

### 2.5 The enforced canonical vocabulary

`config/mappings/normalization.yaml` enums are enforced by the D2 quality gate: a richer source
value is **rejected**, not stored.

| Field | Permitted values | Missing values that matter downstream |
|---|---|---|
| `deals.stage` | `qualification`, `negotiation`, `won` | **no `lost`** — there is no negative class for win/loss modelling |
| `support_tickets.priority` | `medium`, `high` | no `low`, `critical` |
| `support_tickets.status` | `open`, `resolved` | no `in_progress`, `reopened`, `closed` |
| `projects.status` | `planning`, `in_progress` | no `completed`, `cancelled` |
| `customers.status` | `active`, `inactive` | no churn date, no churn reason, no contract end date |

Entities that do not exist at all: invoices, payments, usage/telemetry, activities
(calls/emails/meetings), renewals, subscriptions, headcount plans, budgets.

### 2.6 The dataset, measured

233 rows: 1 organization, 24 employees, 50 customers, 44 deals, 22 projects, 80 support
tickets, 12 documents. (Earlier planning notes quoted 23/40/20/10; the README figures above are
correct and are pinned by `tests/unit/test_i2_readme.py`.)

| Measurement | Value | Why it matters |
|---|---|---|
| Deal currencies | INR 30, USD 13, EUR 1 | **No FX rate table exists anywhere.** Monetary aggregation across customers is not defensible until §6.3 is built. |
| Deal amounts | min 1,102 · median 327,750 · max 12,797,000 | Three orders of magnitude, mixed currency |
| `won` deals | 14, across 8 distinct months, 2023-03 → 2026-06 | Not a forecastable time series |
| Inactive customers | 4 (CUST-002, 013, 027, 034) | **All four have zero tickets and zero deals** |
| Customers with no tickets | 15 of 50 | |
| Customers with no deals | 22 of 50 | |
| Ticket date range | 2026-01-06 → 2026-08-27 | The dataset clock is frozen; see §2.7 |
| Ticket status | 67 resolved, 13 open | |

### 2.7 The decaying-clock problem

The most recent ticket is dated **2026-08-27**. Real time keeps moving. Measured against a
`now()` of 2026-09-18:

| Recency window from `now()` | Customers with ≥1 ticket |
|---|---|
| 14 days | **0** |
| 30 days | 3 |
| 60 days | 11 |
| 90 days | 18 |

> **Binding consequence:** no intelligence module may call `now()` or `today()`. Every
> computation takes an explicit `as_of` date. The default is resolved as: explicit argument →
> environment variable → `max(support_tickets.created_at)` within the scoped source system.
> This is what keeps every scenario reproducible and keeps the demo alive indefinitely.

---

## 3. Data feasibility verdict per proposed capability

| Capability | Verdict | Evidence and reasoning |
|---|---|---|
| Support-pressure risk signals (open/high counts, ticket velocity, recency) | **Supported now** | 80 tickets with dates, priority, status, category and a canonical customer FK |
| Policy escalation state | **Supported now** | DOC-003 states a machine-checkable rule: *"Customers raising three or more tickets within 14 days are escalated to their account owner."* Exactly one customer in the dataset satisfies it (CUST-007, 5 tickets in a 9-day span) |
| SLA resolution-target breach | **Supported now** | DOC-003 gives targets (high: 1 business day; medium: 5 business days); tickets carry created/resolved dates. Widespread: 23 customers / 38 breaches at as_of 2026-09-18 — a supporting signal, not a discriminator (§4.3) |
| Customer ↔ deal / ticket / project context | **Supported now** | Canonical FKs (§2.1) |
| Account-owner and escalation path (owner → manager) | **Supported with derived features** | Source-key joins (§2.2), resolved in one source system |
| Customer ↔ document evidence links | **Supported with derived features** | No FK (§2.3). DOC-005, DOC-006 and DOC-009 contain the literal token `CUST-007`; DOC-010 does not mention Meridian at all. See §7 |
| Per-currency commercial exposure | **Supported now** | Deal amount, currency, probability, stage, close date — reported **per currency**, never summed |
| Cross-customer monetary ranking / total pipeline value | **Requires additional data** | Needs the FX rate table and normalization policy of §6.3 |
| Cross-functional narrative brief with citations | **Supported now** | All facts resolve to a canonical record+field or a document id+span |
| Natural-language enterprise Q&A | **Supported with derived features** | Needs a retrieval surface and a language model; the underlying facts exist |
| Multi-hop / path queries over the org graph | **Requires additional data** | The manager tree exists but only 24 employees and one organization; no cross-entity paths deep enough to need a graph engine |
| **Churn prediction** | **Not defensible yet** | 4 positive labels, **all with empty feature vectors** (zero tickets, zero deals); no `lost` deal stage so no negative class; no churn date; no longitudinal state. Any metric would be an artifact of the seed generator |
| **Revenue / demand forecasting** | **Not defensible yet** | 14 `won` deals over 8 distinct months in 2 currencies, with no FX policy and no actual close dates. No series exists to forecast |
| Anomaly detection | **Not defensible yet** | No time series and no baseline period |
| Resource / headcount forecasting | **Not defensible yet** | No headcount history, no allocation records, no capacity entity |

---

## 4. Intelligence strategy: deterministic first

### 4.1 The rule

Intelligence is deterministic unless a specific question provably cannot be answered
deterministically. VS-01 through VS-03 are fully deterministic. This is not conservatism — it
is the project's central claim. The platform's value proposition is *explainable,
source-grounded executive reasoning*, and a deterministic rule engine whose every output names
the rules and records that produced it is a stronger demonstration of that claim than a model
whose reasoning must be reconstructed after the fact.

### 4.2 No false precision

Risk is expressed as an **ordinal band** — `NONE` / `WATCH` / `ELEVATED` / `CRITICAL` — never
as a probability or a percentage. A statement like "87% probability of churn" is forbidden
project-wide until §6 delivers a model with a stated evaluation methodology, and even then it
may only be said about the synthetic analytical dataset, never about a demo customer.

Bands are assigned by a **versioned decision table in configuration**, mirroring how D1/D2
rules already live in `config/`. Each band assignment emits the list of satisfied rules; that
list *is* the explanation. There are no tuned weights, because arbitrary weights are
unfalsifiable and indefensible under questioning.

### 4.3 Risk and impact are separate axes — never blended

This is a measured finding, not a stylistic preference.

On support pressure, CUST-007 is unambiguously first: 4 open tickets, 4 high priority, 4 in the
last 30 days; the next-worst customer has 2 open. On commercial exposure it is near the bottom:
**22nd of the 23 customers holding active deals** by weighted exposure. Restricted to one
currency so the comparison is honest, DEAL-001 is 12th of the 13 USD deals by amount, and
CUST-007's USD weighted exposure (4,825.30) is exactly the median of the 7 USD customers. A
cross-currency portfolio ranking is **not computable** until §6.3 delivers the FX rate set — the
"median 327,750" in §2.6 is a mixed-currency figure and must never be compared against a USD
amount. Meanwhile CUST-015 (Unity Pharma) carries ~8.96M of weighted exposure and CUST-031
(Vertex Foods) ~1.77M with a single open ticket.

A single blended score would therefore demote Meridian and surface Unity Pharma — and it would
be *correct* to do so given a badly specified objective. The design consequence:

- **Risk band** is computed from relationship-health signals only. Money is not an input.
- **Commercial impact** is reported alongside as context, per currency, and is used only to
  decide *executive-worthiness* and ordering among equally-banded customers.
- A test asserts that the risk ranking does not change when deal amounts are perturbed. This
  permanently guards against a blended score being reintroduced.

### 4.4 Active deterioration vs chronic backlog

A second measured trap. TKT-010 (CUST-009) and TKT-005 (CUST-048) are single `medium` tickets
left open since January 2026 — 155 and 175 business days past target at as_of 2026-09-18. A
naive "worst SLA breach age" signal ranks those customers above Meridian.

So the signal set must distinguish:

- **Active deterioration** — ticket velocity within a bounded window, plus open high-priority
  tickets. This is what drives the band.
- **Chronic backlog** — a long-stale open ticket. Reported as a separate observation. It never
  drives the escalation band.

The primary discriminator is the DOC-003 policy escalation state, constrained to a recency
lookback from `as_of` (default 90 days) so that a burst in January 2026 does not escalate a
customer forever.

---

## 5. Graph strategy

**Decision: PostgreSQL now, behind a substrate-agnostic interface. Neo4j only when a slice
needs it.**

### 5.1 Why not Neo4j in VS-01

Every question VS-01 asks is answered by three foreign keys and source-key joins over the six
carrier fields of §2.2, five of which VS-01 actually models. A second
datastore would add a synchronisation path from Postgres, its own consistency and failure
modes, a second test harness, and the risk of two divergent answers to the same question —
buying nothing, because there is no multi-hop traversal in the slice.

### 5.2 What is built instead

An **enterprise relationship model**: a read-only service exposing canonical entities as typed
nodes and their relationships as typed edges, computed over Postgres. Its value over raw SQL is
not performance; it is that **every edge carries its own provenance**:

| Edge basis | Meaning |
|---|---|
| `CANONICAL_FK` | A Layer 1 canonical foreign key — provenance-backed |
| `SOURCE_KEY_JOIN` | Joined on a `source_id` string within one source system |
| `DERIVED_TEXT_MATCH` | Inferred from document text (§7) — carries the matched token |
| `DERIVED_TOPIC_MATCH` | Inferred from category overlap — supporting evidence only |

This is what lets an executive brief state not only *what* is related but *how that
relationship was known*. That is the explainability spine of the whole platform, and it is the
honest justification for a relationship layer existing at all.

### 5.3 Trigger for introducing Neo4j

A slice requires variable-length path queries, shortest-path or community detection over
entities, and the equivalent recursive SQL is measurably unmanageable. Until then, introducing
Neo4j is deviation from the proposal that must be **documented as a deliberate, justified
engineering decision**, not hidden.

---

## 6. ML strategy — the versioned Layer 2 analytical projection

**Status: PROPOSED. Deliberately not implemented. Reasoned through here before any build.**

### 6.1 The decision

Layer 1 stays frozen. Its D1 vocabulary is **not** widened to satisfy ML requirements. Instead,
Layer 2 gains a separate, versioned **analytical projection** in its own PostgreSQL schema
(`analytics`), holding longitudinal customer states, lifecycle transitions, lost deals and
monthly revenue observations. The projection is generated from the Layer 1 enterprise model
plus a documented synthetic temporal extension with a fixed seed and known ground truth.

The separation of concerns this buys:

- **Layer 1** — what the enterprise currently knows.
- **Layer 2 analytics** — what the analytical system derives and models.
- **ML dataset** — versioned analytical data with explicitly documented synthetic assumptions.

And it buys the two things that matter most: no false claim that 233 rows support churn
prediction, and no contamination of the frozen canonical contract.

### 6.2 Two categorically different kinds of analytical row

Conflating these is the primary failure mode of the whole approach.

| Origin | Definition | Example |
|---|---|---|
| `DERIVED` | Deterministically recomputable from Layer 1 rows | Monthly ticket counts per customer; open-ticket state at month end |
| `SYNTHETIC` | No Layer 1 antecedent; produced by the generator | Months before the observed window; `lost` deals; churn events |
| `HYBRID` | A derived row carrying synthetic fields | A real customer's month enriched with a generated usage figure |

Every analytical row carries `origin`, the generator version, the seed, and the Layer 1 record
ids it descends from. A `dataset_versions` table pins (generator version, seed, parameter set,
**Layer 1 snapshot fingerprint**) — the fingerprint being a hash over all canonical
`record_hash` values plus per-entity counts.

Required properties, each a test:

1. Same seed + same Layer 1 snapshot → **byte-identical** analytical dataset.
2. Every `DERIVED` row is recomputable from Layer 1 alone.
3. Every `SYNTHETIC` row is reproducible from (seed, version, parameters) alone.
4. The generator is **read-only against Layer 1**, enforced by a static boundary test in the
   style of G2 — it must not be able to import a write path.
5. A lineage report answers, for any analytical figure, "which Layer 1 records is this made of,
   and which part of it was generated?"

### 6.3 FX normalization is a shared component, needed earlier than ML

VS-02 cannot state a pipeline value without it, so FX is **not** an ML-slice concern. An
`fx_rates` reference table — `(currency, as_of_date, rate_to_base, rate_set_version)` — with a
declared base currency is delivered in VS-02 and reused by the projection. Every monetary
aggregate must report its base currency and rate-set version, and the rate set is labelled a
**stated assumption**, never a fact. Silently mixing INR, USD and EUR is forbidden everywhere.

### 6.4 The circularity trap, and the defences

> If churn labels are generated by a rule and a model is then trained to predict them, a good
> score means the model recovered the rule its author wrote. This is circular, and it is the
> first thing an examiner will find.

The defences, all implementable:

1. **Publish the ceiling.** Inject controlled stochasticity and label noise so the learnable
   signal is bounded below 100%, and report the **Bayes-optimal ceiling implied by the
   generator**. The result becomes "the model reaches X against a known ceiling of Y" — a
   quantified finding instead of a meaningless 0.97.
2. **Split by time, never randomly.** Features from `[t-6, t)`, label in `[t, t+3)`, with an
   explicit gap between them. Random splits leak by construction in longitudinal data.
3. **Also hold out whole customers**, to measure cold-start behaviour separately.
4. **Always report the naive baseline** — majority class for churn; seasonal-naive and
   last-value for revenue. The proposal's §9 asks for "measurable improvement over a naive
   baseline"; with a known generator this sentence can be satisfied honestly.
5. **Ablate by signal family** (support pressure / commercial / tenure), so the finding is
   *which* generative structure was recovered, not just a number.
6. **Commit the generator.** The result is only reproducible if the data-generating process is
   in the repository and versioned.

### 6.5 Leakage risks specific to this design

- If a synthetic churn event is generated *after* elevated ticket counts, and the model is also
  fed ticket counts from the churn month itself, the label leaks into the features. Feature
  windows must end strictly before the label window.
- If the generator uses a customer's segment to decide churn, and segment is also a feature,
  the model recovers a lookup, not a pattern. Generator inputs must be documented so that
  feature/label overlap is visible and reviewable.
- Derived rows computed at month granularity from Layer 1 tickets must be computed `as_of` the
  month boundary, not with full knowledge of later months.

### 6.6 What may and may not be claimed

**Defensible claim:** *"The feature-engineering, training and evaluation pipeline is correct,
reproducible, and recovers the known generative structure of a documented simulated dataset,
approaching the ceiling that structure implies, and beating the naive baseline by a measured
margin."*

**Forbidden claims:** any transfer to real enterprises; any absolute churn rate; any comparison
to industry benchmarks; any churn probability attached to a demo customer by name; any
suggestion that the longitudinal extension is real historical enterprise data. Every reported
metric must be adjacent to the sentence identifying the dataset as synthetic with known ground
truth.

### 6.7 Model runtime decision (language models)

**Decision: templated generation first; every model call behind one interface; provider
deferred.**

- **VS-01 uses no language model at all.** The executive brief is rendered from templates over
  deterministic facts. This makes the slice reproducible, unit-testable, offline and free — and
  it makes prompt injection *structurally impossible* rather than merely mitigated.
- All later model use sits behind a single `LanguageModel` interface whose **default
  implementation is a deterministic fake**. Nothing downstream knows the provider.
- A **committed response cache**, keyed by a hash of (prompt, model, parameters), makes demos
  network-independent and tests deterministic. This is the mechanism that de-risks whichever
  provider is eventually chosen.
- Provider choice for VS-04/VS-05 is deferred. Free hosted inference tiers (for example Google
  AI Studio, Groq, OpenRouter free models, HuggingFace serverless inference) require no local
  storage and no subscription, which matches the project's constraints.
- **Rejected: hosting an open model in Google Colab with weights on Google Drive.** Assessed and
  turned down for four reasons: Drive's FUSE mount is typically *slower* for multi-GB weight
  loads than downloading from the HuggingFace Hub inside the session, so the storage buys a
  slower cold start rather than a faster one; serving a local FastAPI application from Colab
  requires an external tunnel and runs against Colab's terms for long-running remote serving;
  free-tier sessions can be denied a GPU, idle-disconnect or throttle, which is the worst
  possible dependency during a review presentation; and 10–30 minutes of session and model
  cold start would precede every demo.
- **Colab is retained for ML training** in VS-06–VS-08, where it is genuinely the right tool:
  batch training tolerates cold starts and disconnects, and Google Drive is a good home for
  trained artifacts and metrics. Colab is for training, not for serving.
- An offline fallback, if one is ever needed: a 1.5–3B instruct model in Q4 GGUF (~1–2 GB) on
  CPU. Weak, but genuinely offline.

---

## 7. Retrieval and evidence strategy (RAG)

**Decision: deterministic evidence selection first. No embeddings, no vector store, before
VS-05.**

### 7.1 Why no vector search yet

There are 12 documents totalling roughly 3,900 characters of body text. Embedding a corpus that
fits in a single screen, to retrieve from it approximately, when it can be selected from
exactly, would be indefensible under questioning.

### 7.2 How documents are linked to customers

`documents` has no customer reference (§2.3), so links are **derived in Layer 2 and recorded in
a link table**, leaving Layer 1 untouched. Two bases, with different standing:

| Basis | Rule | Standing | Measured result |
|---|---|---|---|
| `DERIVED_TEXT_MATCH` (id token) | The canonical `source_id` token appears in title or body | High precision; may derive signals | DOC-005, DOC-006, DOC-009 each contain `CUST-007` |
| `DERIVED_TEXT_MATCH` (exact name) | The customer's **full** name matches exactly | High precision | Substring matching is explicitly forbidden: "Westbrook Textiles", "Northstar Textiles" and "Evergrid Textiles" (CUST-039) exist alongside "Meridian Textiles" |
| `DERIVED_TOPIC_MATCH` | Document topic overlaps the customer's ticket categories | Supporting evidence only — may **never** derive a signal | DOC-010 (nightly-sync postmortem) is the root-cause evidence for TKT-075 but never names Meridian |

Every link records its basis, the matched token and its character offset, so a reviewer can
verify any link by hand.

### 7.3 How policy documents are cited

Structurally, not by retrieval. The SLA rule configuration names DOC-003 as its source, so a
brief that applies the escalation rule cites DOC-003 **because the rule came from it**. This
eliminates an entire class of failure: the citation cannot drift from the rule, because the rule
carries the citation.

### 7.4 The grounding guarantee

Every asserted fact in any generated output must carry a machine-resolvable reference to either
a canonical record id plus field name, or a document id plus character span. A test parses every
generated brief and resolves every citation; an unresolvable citation fails the build.

### 7.5 The answer-leakage test

DOC-005 states the Meridian escalation conclusion *in prose*. A system that retrieved DOC-005
and paraphrased it would look correct while having computed nothing.

> **Mandatory test:** with DOC-005 removed from the corpus, the risk band, every signal value
> and the escalation state must be **unchanged**. This proves the conclusion is computed from
> ticket records rather than parroted from a document. It is the single most valuable test in
> VS-01.

### 7.6 Trigger for introducing embeddings and a vector store

VS-05 (Enterprise Copilot) needs open-vocabulary retrieval over a corpus large enough that
exact selection fails. Until a document corpus exceeds roughly 200 documents, or a slice needs
paraphrase-tolerant matching, `pgvector` inside the existing PostgreSQL instance is the first
step — not Milvus or FAISS, which would add a datastore for a corpus this size.

---

## 8. Agent strategy

**Decision: agent-shaped contracts now, language-model agents later, fourteen agents never
without fourteen responsibilities.**

### 8.1 The honest position

VS-01 needs no LLM agents. What it needs is **scope separation**: a module that judges support
health must not be able to see deal amounts, or it will smuggle money into the risk band (§4.3).
That separation is an architectural property worth building immediately; the reasoning engine
behind it can start deterministic.

So VS-01 implements three **analyst modules with agent contracts** — a declared and *enforced*
data scope, a declared tool surface, and a structured output schema:

| Module | May see | Owns |
|---|---|---|
| `SupportRiskAnalyst` | Support tickets, SLA policy rules | Risk band, signal values, SLA breaches, escalation state |
| `CommercialContextAnalyst` | Deals, projects, contract documents | Per-currency exposure, deal stage and probability, contract renewal terms |
| `ExecutiveReconciler` | Only the two structured outputs, plus customer identity | Executive-worthiness, ordering, action selection, the brief |

Scope is a test, not a comment: a test asserts `SupportRiskAnalyst` cannot reach the deals
table.

### 8.2 Conflict handling

**Revised 2026-09-18 after the VS-01 grilling.** v1 of the VS-01 plan deferred conflict to
VS-04, on the grounds that manufacturing disagreement would be dishonest. That was wrong: a
genuine conflict is already present in the committed data. Sales reads DEAL-001 as a
90%-probability negotiation to accelerate; Support reads an active DOC-003 escalation with three
open high-priority tickets past their SLA resolution target and wants deal pressure paused; and
DOC-009 records the customer tying the deal decision to those tickets being resolved. Two
incompatible actions on one object.

So **VS-01 owns conflict reconciliation**: a versioned conflict policy that detects incompatible
proposed actions over the same object, resolves them by a stated rule citing the documents that
justify it, and **preserves the losing position as recorded dissent** rather than averaging it
away. Without this the slice is a report with citations, not a proof of the platform's thesis.

VS-04 then *extends* a mechanism that already exists — more functions, three-way and cyclic
conflicts, and model-generated narrative over an already-decided outcome — rather than
inventing it from nothing.

### 8.3 Actions come from a closed catalogue

A recommendation is never free text. It is an entry from a versioned catalogue, each entry
declaring its preconditions in configuration:

`SCHEDULE_EXECUTIVE_SPONSOR_CALL` · `ASSIGN_DEDICATED_SUPPORT_OWNER` ·
`PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` · `ESCALATE_TO_ACCOUNT_OWNER_PER_SLA` ·
`REVIEW_INVOICE_DISPUTE` · `NO_ACTION`

This makes recommendations testable and explainable, and it bounds what the system can ever
propose. (The catalogue is grounded in the dataset's own narrative: DOC-009 already records
"executive sponsor call next week".)

### 8.4 On "fourteen agents"

The proposal names fourteen. An agent will be created when a slice has a responsibility for it
to own — never to reach a count. The final report will state how many agents exist, what each
owns, and why the remainder were not built. That is a stronger position than fourteen shallow
prompt wrappers.

---

## 9. Governance and human-approval strategy

### 9.1 The invariant

> **No slice from VS-01 to VS-05 contains an executor.** No module may send an email, call a
> third-party API or write to a source system. This is enforced the way G2 enforces read-only
> connectors: a static boundary test that fails if a decision module imports an outbound client.

Recommendation and execution are separated by the absence of an executor, not by a flag. A
rejected recommendation cannot accidentally execute because nothing can execute.

### 9.2 Approval binds to content, not to an identifier

A decision record stores `(brief_id, payload_hash, actor, decision, decided_at, note)`. Approval
binds to the hash of the **decision payload** — the facts, positions, conflict, resolution and
citations — and explicitly **not** to the rendered narrative, which is a view: excluding
timestamps and `template_version` means a template edit cannot invalidate a prior approval, while
regenerating a brief with different facts still invalidates it, because it cannot be inherited by
a changed recommendation. See `CONTEXT/VS01_IMPLEMENTATION_PLAN.md` §A17. Decisions
are append-only; a decision is never mutated, only superseded by a new row that names its
predecessor.

### 9.3 The authentication gap, stated plainly

Layer 1 has no authentication, by documented design. An approval endpoint therefore records an
**asserted** actor identity, not a verified one.

> Authentication is a hard prerequisite before any executor is ever built. Until then the
> approval boundary is a governance *record*, not a security control, and the documentation must
> say so in exactly those terms.

### 9.4 What must never become autonomous

Contacting a customer; modifying a CRM or ERP record; issuing credit, discounts or refunds;
changing a contract; any communication with a person outside the company. These remain
human-executed for the lifetime of the project.

---

## 10. The complete vertical-slice roadmap

Dependencies are strict: a slice may not begin until its predecessors are accepted.

```
Layer 1 (IMPLEMENTED)
   │
   ├─ VS-01  Customer Risk & Executive Escalation          PLANNED  ← next
   │     builds: relationship model, signal engine, evidence links,
   │             analyst contracts, brief, approval record
   │
   ├─ VS-02  Revenue & Pipeline Intelligence                PROPOSED
   │     builds: FX normalization (shared), pipeline aggregation
   │
   ├─ VS-03  Executive Account 360                          PROPOSED
   │     builds: composition over VS-01 + VS-02; little new capability
   │
   ├─ VS-04  Cross-Functional CEO Decision                  PROPOSED
   │     builds: genuine conflict reconciliation; first real LLM use
   │
   ├─ VS-05  Enterprise Copilot                             PROPOSED
   │     builds: open-vocabulary retrieval, pgvector, grounded Q&A
   │
   └─ FUTURE / CONDITIONAL — blocked on the analytical projection
         VS-06  Longitudinal Analytical Projection
         VS-07  Churn Modelling            (depends on VS-06)
         VS-08  Revenue Forecasting        (depends on VS-06 + VS-02 FX)
```

### 10.1 VS-01 — Customer Risk & Executive Escalation · PLANNED

**Full specification: `CONTEXT/VS01_IMPLEMENTATION_PLAN.md`.** Summary only here.

| Dimension | Content |
|---|---|
| **Objective** | Surface, with evidence, the customers whose service relationship is deteriorating while commercial exposure is live, and produce an approvable executive brief |
| **Executive question** | "Which customers currently require executive attention, why, and what should we do?" |
| **Demo question** | "Why is Meridian Textiles at risk, and what should the CEO do?" |
| **Persona** | CEO / executive sponsor; secondarily the account owner (EMP-007) and Head of Customer Support (EMP-004) |
| **Trigger** | Explicit API call or CLI command with an `as_of` date. No scheduler |
| **Data sources** | Layer 1 canonical tables only, scoped to one `source_system` |
| **New capability** | Relationship model with per-edge provenance; deterministic signal engine; derived document links; two scope-isolated analysts emitting positions; **conflict detection and reconciliation with recorded dissent**; content-hash-bound approval record |
| **ML** | None |
| **Graph** | Postgres-backed relationship service. No Neo4j |
| **Retrieval** | Deterministic selection. No embeddings |
| **Human boundary** | Brief is `DRAFT`; approval/rejection recorded against a content hash; no executor exists |
| **Acceptance** | At the pinned `as_of`, CUST-007 is the only `CRITICAL` customer and the only one executive-worthy; its brief cites 5 tickets in 9 days, 4 open, **3 open high-priority** (4 high in total), DEAL-001 in negotiation, DOC-003's escalation rule and DOC-006's renewal terms; the Sales/Support conflict is detected, resolved by a named policy and the losing position recorded as dissent; every citation resolves; removing DOC-005 changes nothing; a healthy customer yields `NONE`; ranking is invariant to deal amounts; the payload hash is stable across runs |
| **Out of scope** | Churn probability, forecasting, Neo4j, embeddings, LLM, multi-source aggregation, cross-currency totals, scheduling, notification, authentication, UI beyond OpenAPI |

### 10.2 VS-02 — Revenue & Pipeline Intelligence · PROPOSED

| Dimension | Content |
|---|---|
| **Objective** | State the shape and concentration of open pipeline, and where commercial exposure coincides with relationship risk |
| **Executive question** | "What revenue exposure requires attention?" |
| **Why it is second** | It delivers FX normalization, which VS-03 and VS-08 both need, and it is the natural consumer of VS-01's risk bands |
| **New capability** | `fx_rates` reference table and normalization service (§6.3); per-stage and per-owner aggregation; concentration measures; expected-close exposure by period; risk-adjusted pipeline view joining VS-01 bands |
| **Data requirements** | An explicit FX rate set with a declared base currency and as-of date, labelled a stated assumption. Without it, no cross-currency figure may be produced |
| **ML** | **None.** This slice is named *Pipeline Intelligence*, not *Revenue Forecasting*. Forecasting is VS-08 and is conditional |
| **Key constraints** | 30 of 44 deals are INR, 13 USD, 1 EUR; there is no `lost` stage, so no win-rate and no stage-conversion analysis is possible; `won` deals carry only an expected close date, not an actual one |
| **Acceptance** | Every monetary aggregate names its base currency and rate-set version; totals reconcile to the per-currency breakdown; the absence of a `lost` stage is surfaced as an explicit limitation in the output, not silently ignored; DOC-004's stated INR pipeline figure is reproduced from the records |
| **Out of scope** | Forecasting, win-rate, stage-conversion, quota, territory analysis |

### 10.3 VS-03 — Executive Account 360 · PROPOSED

| Dimension | Content |
|---|---|
| **Objective** | Assemble everything known about one customer into a single briefing for an executive review |
| **Executive question** | "What does the CEO need to know about this customer before an executive review?" |
| **New capability** | Very little — this is deliberately a **composition slice**, proving the VS-01 and VS-02 components compose without new infrastructure |
| **Adds** | Full customer neighbourhood; relationship timeline over `as_of`; people map (account owner, ticket assignees, deal owner, their managers); document dossier; contract terms summary |
| **Data requirements** | None new |
| **Known gap** | CUST-007 has **no project**, so the project section of the flagship account's 360 will be legitimately empty. The template must render emptiness as a stated absence, never as a zero or a silent omission |
| **Acceptance** | Generated for all 50 customers without error; every section either cites evidence or states that no evidence exists; no section fabricates a figure; output is deterministic at a fixed `as_of` |
| **Out of scope** | New signals, new stores, predictions |

### 10.4 VS-04 — Cross-Functional CEO Decision · PROPOSED

| Dimension | Content |
|---|---|
| **Objective** | Reconcile genuinely conflicting functional conclusions about one business situation into one recommendation with the disagreement preserved |
| **Executive question** | "What should the organization do when functions disagree about the same situation?" |
| **Relationship to VS-01** | VS-01 already owns two-function conflict detection, a versioned conflict policy and recorded dissent. VS-04 **extends** that mechanism rather than introducing it |
| **New capability** | Three or more functions; three-way and cyclic conflicts, which a pairwise policy cannot resolve; precedence between competing policy entries; and the first genuine language-model use — narrative synthesis over facts and an action already decided deterministically |
| **Agent boundary** | Functional analysts still may not see each other's data; only the reconciler sees both. The LLM never selects the action — it renders an explanation of an action chosen deterministically |
| **Acceptance** | A three-way conflict is resolved and every position is stated with citations; the reconciliation rule that resolved it is named; a reviewer can reconstruct the decision without the model; removing the LLM degrades prose only, never facts or the chosen action |
| **Out of scope** | Fourteen agents; autonomous execution; letting the model choose the recommendation |

### 10.5 VS-05 — Enterprise Copilot · PROPOSED

| Dimension | Content |
|---|---|
| **Objective** | Answer open-vocabulary executive questions across the enterprise with traceable, grounded answers |
| **Executive question** | "Can an executive ask questions across the enterprise and get answers they can verify?" |
| **New capability** | Question routing across structured queries, relationship traversal and document retrieval; answer composition with mandatory citations; **refusal** when evidence is insufficient |
| **Infrastructure** | First justified embedding use — `pgvector` inside the existing PostgreSQL instance, not Milvus or FAISS, given corpus size |
| **Security** | The first slice where retrieved document text reaches a model prompt. Requires: retrieved text rendered as quoted data with delimiters, never as instruction; an instruction-injection test suite using adversarial text planted in a fixture document; a tool allowlist per question type; every query scoped so no answer can cross into data the question did not ask for |
| **Acceptance** | A fixed question set, each with a known correct answer and required citations; every answer's citations resolve; questions whose answer is absent from the data are **refused rather than guessed**; a planted injection in a fixture document does not alter tool calls or answers |
| **Out of scope** | Write actions, multi-turn memory, a chat UI beyond a minimal surface |

### 10.6 VS-06 — Longitudinal Analytical Projection · FUTURE / CONDITIONAL

| Dimension | Content |
|---|---|
| **Objective** | Create the versioned `analytics` schema and the documented synthetic temporal extension that VS-07 and VS-08 require (§6) |
| **Precondition** | Explicit approval to build it, and agreement on the academic framing of §6.6 |
| **Delivers** | `analytics` schema; `dataset_versions` with Layer 1 snapshot fingerprint; monthly customer state; lifecycle transitions; `lost` deals; monthly revenue observations; per-row lineage; the lineage report; the read-only-against-Layer-1 boundary test; the reproducibility test |
| **Acceptance** | Same seed + same snapshot yields byte-identical output; every `DERIVED` row recomputes from Layer 1; every `SYNTHETIC` row reproduces from (seed, version, parameters); the lineage report resolves any figure to its Layer 1 ancestors and its generated components; the generator provably cannot write to Layer 1 |
| **Out of scope** | Any model. This slice produces data and lineage only |

### 10.7 VS-07 — Churn Modelling · FUTURE / CONDITIONAL

Depends on VS-06. Requires per §6.4–6.6: time-based splits with a gap, customer-level holdout,
a published Bayes-optimal ceiling, majority-class baseline, signal-family ablations, and the
synthetic-data disclosure adjacent to every metric. **Not to be started before VS-06 is
accepted.**

### 10.8 VS-08 — Revenue Forecasting · FUTURE / CONDITIONAL

Depends on VS-06 and VS-02's FX policy. A Temporal Fusion Transformer is **not** justified by
any dataset this project will plausibly have; the honest progression is seasonal-naive baseline
→ classical (ETS/ARIMA) → gradient boosting on lag features, with the model chosen by measured
performance against the baseline and the choice documented. Reporting must state the series
length, its synthetic origin and the FX assumption.

---

## 11. Shared vs slice-local infrastructure

| Component | Standing | Introduced in | Rule |
|---|---|---|---|
| Relationship model with per-edge provenance | **Shared** | VS-01 | Every slice reads relationships only through it |
| `as_of` resolution | **Shared** | VS-01 | No module may call `now()` |
| Evidence/citation contract | **Shared** | VS-01 | Any generated output must resolve every citation |
| Derived document link table | **Shared** | VS-01 | New bases may be added; existing bases may not change meaning |
| Analyst-contract base (scope + tools + output schema) | **Shared** | VS-01 | Scope enforcement is a test, not a convention |
| Approval / decision record | **Shared** | VS-01 | Append-only; binds to content hash |
| FX normalization | **Shared** | VS-02 | Never aggregate mixed currency without it |
| Signal definitions | **Slice-local first** | VS-01 | Promote to shared only on second use |
| Brief templates | **Slice-local** | each slice | Never generalised prematurely |
| Language-model interface + response cache | **Shared** | VS-04 | Deterministic fake stays the default |
| Embeddings / `pgvector` | **Slice-local** | VS-05 | Do not generalise until a second slice needs it |
| `analytics` schema + lineage | **Shared within ML slices** | VS-06 | Never mixed into canonical tables |

**Generalisation rule:** a capability is promoted from slice-local to shared on its **second**
real use, never on its first anticipated use.

---

## 12. Deferred infrastructure and the trigger for each

| Technology | Status | Trigger that would justify it |
|---|---|---|
| Neo4j | Deferred | A slice needs variable-length path, shortest-path or community queries |
| Milvus / FAISS | Deferred, likely never | Corpus outgrows `pgvector` in the existing PostgreSQL instance |
| `pgvector` | Deferred to VS-05 | Open-vocabulary retrieval where exact selection fails |
| Redis | Deferred | A measured latency problem that caching demonstrably solves |
| LangGraph / CrewAI | Deferred | Three or more agents with genuine dynamic control flow, where explicit orchestration code has become the bottleneck |
| Temporal / n8n | Deferred, likely never | Durable multi-day workflows with retry semantics beyond a single request |
| Event bus | Deferred, likely never | More than one independent consumer of the same change stream |
| Model routing | Deferred | Two or more providers in use with measurably different cost/quality trade-offs |
| Feature store | Deferred, likely never | Features shared across several models **and** an online/offline consistency requirement |
| React frontend | PROPOSED | Decide when a slice's value cannot be shown through the API and a brief |
| Authentication | **Blocking prerequisite** | Required before any executor is ever built (§9.3) |
| Cross-source entity resolution | Deferred | A slice must aggregate the same real-world entity across two source systems |

---

## 13. Future data requirements (what must exist before each ML claim)

### 13.1 Before churn modelling

| Requirement | Why |
|---|---|
| 24–36 months of monthly customer state | A single snapshot cannot express deterioration over time |
| Explicit lifecycle transitions with dates | `active`/`inactive` with no date or reason is not a label |
| A `lost` deal outcome | Currently absent; there is no negative class |
| Churned customers with non-empty feature histories | All 4 current inactive customers have zero tickets and zero deals |
| Enough positives to split | 4 positives cannot support a train/test split at all |
| Documented generative process, fixed seed, published ceiling | Required for §6.6's defensible claim |
| Feature/label window separation with a gap | Prevents structural leakage |

### 13.2 Before revenue forecasting

| Requirement | Why |
|---|---|
| Monthly revenue observations over 24–36 months | 14 won deals over 8 distinct months is not a series |
| Actual close dates, not just expected | `won` deals carry only `expected_close_date` |
| FX rate set with declared base and as-of date | 3 currencies, no rate table |
| Seasonal-naive and last-value baselines | §9 requires improvement over a naive baseline |
| A stated forecast horizon and evaluation protocol | Otherwise the metric is unfalsifiable |

### 13.3 Before anomaly detection or resource forecasting

A baseline period, plus entities that do not exist at all today: usage/telemetry, invoices and
payments, activities, headcount and capacity records. Not in scope for this project.

---

## 14. Project-wide out-of-scope boundaries

1. Write-back to any source system. Layer 1's read-only guarantee extends to every slice.
2. Autonomous execution of any recommendation.
3. Any churn probability or forecast attached to a demo customer by name.
4. Cross-currency monetary aggregation before the FX policy exists.
5. Cross-source-system aggregation before entity resolution exists.
6. `now()` anywhere in an intelligence module.
7. Claims of production readiness. The system is a prototype; limitations are documented.
8. Fourteen agents created to reach a count.
9. Any datastore introduced without a slice that needs it.
10. Widening Layer 1's D1 vocabulary to satisfy an analytical requirement — the analytical
    projection exists precisely so this never happens.

---

## 15. Grilling record — what survived, changed and was rejected

### 15.1 Survived

- **Vertical-slice development.** Strongly correct for this project's review calendar and its
  need for demonstrable outcomes.
- **VS-01 as the first slice.** The dataset's strongest, cleanest scenario, and the one that
  exercises every architectural layer while needing no new infrastructure.
- **Risk framed as health, not churn prediction.** The only defensible framing given the data.
- **Human approval as a hard boundary.**
- **The Meridian Textiles scenario.** It holds up better than expected: exactly one customer in
  the dataset satisfies DOC-003's documented escalation rule.

### 15.2 Changed

| Proposed | Changed to | Reason |
|---|---|---|
| Neo4j knowledge graph in Layer 2 | Postgres relationship service behind a substrate-agnostic interface | VS-01's queries are 3 FKs and 5 modelled source-key joins (§2.2); a second store buys nothing |
| `Customer --HAS_DOCUMENT--> Document` edge | Derived link table with recorded basis and confidence, read through the evidence interface — **not** through the relationship API (plan §A9, §A11) | No such relationship exists in Layer 1 (§2.3) |
| Blended numeric risk score | Ordinal band from a versioned decision table, with impact as a separate axis | A blended score demotes Meridian to ~12th and promotes a customer with one open ticket (§4.3) |
| Risk signals evaluated against `now()` | Explicit `as_of` with a dataset-derived default | At `now()` = 2026-09-18, a 14-day window contains **zero** tickets (§2.7) |
| "Customer Risk Agent", "Sales Context Agent" as LLM agents | Deterministic analyst modules with enforced scopes and agent contracts | Calling a rule engine an agent is dishonest; the scope boundary is the part worth building |
| RAG over documents in VS-01 | Deterministic evidence selection; structural policy citation | 12 documents, ~3,900 characters — approximate retrieval over a corpus this size is indefensible |
| ML by widening Layer 1's vocabulary | Separate versioned `analytics` projection with per-row lineage | Keeps the canonical contract frozen and keeps synthetic data honestly labelled |
| Colab + Google Drive model hosting | Templated generation; provider deferred behind an interface with a committed response cache | Drive is slower than HF Hub for weight loads; serving needs a tunnel and runs against Colab's terms; free-tier sessions are the wrong dependency for a live review |
| "Revenue Forecasting ML" as VS-02 | "Revenue & Pipeline Intelligence", forecasting deferred to conditional VS-08 | No series exists to forecast |
| Free-text recommendations | Closed, versioned action catalogue with declared preconditions | Testable, explainable and bounded |

### 15.3 Rejected outright

| Rejected | Why |
|---|---|
| Supervised churn model on the current dataset | 4 positives, **all with empty feature vectors**; no negative class; no longitudinal state. Any metric would measure the seed generator |
| Revenue forecasting on the current dataset | 14 won deals over 8 distinct months, 2 currencies, no actual close dates, no FX table |
| Any percentage churn probability | No labels, and none of the current data would justify calibration |
| Cross-customer monetary ranking before FX | Silently mixing INR/USD/EUR would be a defect presented as a feature |
| Milvus / FAISS / Redis / Temporal / n8n / feature store in the next slices | No slice needs any of them; each would be infrastructure without a question |
| Fourteen agents | Agents without responsibilities are prompt wrappers |
| `HAS_PROJECT` as a load-bearing edge for the flagship demo | CUST-007 has no project |
| SLA breach count as the primary risk discriminator | 23 customers breach at as_of 2026-09-18, and stale January tickets outrank Meridian on breach age (§4.4) |

### 15.4 Open decisions carried forward

1. **Proposal §9 reconciliation.** §9 commits to a churn model and a revenue forecast validated
   against a held-out baseline. The VS-06 → VS-07/VS-08 route can satisfy that sentence
   honestly, but only on synthetic data with the framing of §6.6. Whether that framing is
   acceptable is a decision for the project guide, and it should be raised early rather than at
   submission.
2. **Frontend scope.** The proposal promises a React copilot interface. Undecided whether any
   slice before VS-05 needs a UI beyond OpenAPI.
3. **Language-model provider** for VS-04/VS-05. Deferred by design; the interface makes it cheap
   to answer later.
4. **Authentication timing.** Required before any executor; not required for VS-01–VS-05, which
   have no executor. The point at which it is introduced is undecided.
