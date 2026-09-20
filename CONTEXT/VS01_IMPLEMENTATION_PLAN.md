# VS-01 — Customer Risk & Executive Escalation: Implementation Plan (v2)
**Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
**v1 2026-09-18 · v2 2026-09-18 after adversarial review · v2.1 2026-09-20, M2/M4 boundary**
**Status: PLANNED. Nothing in this document is implemented. Do not begin until approved.**

> Strategy context: `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md`
> Layer 1 state: `CONTEXT/AI_CEO_PROJECT_CONTEXT.md`
>
> **Layer 1 is frozen.** This slice adds new packages, new tables and new routes. It changes no
> canonical schema, no existing migration, no route contract, no D1/D2 semantics and no E1
> status semantics.

---

## 0. What v2 changed, and why

v1 was attacked deliberately. Sixteen defects were found; the material ones are recorded here so
the reasoning is not lost.

| # | Defect in v1 | Severity | Resolution in v2 |
|---|---|---|---|
| 1 | **VS-01 did not prove the AI CEO concept.** Two analysts that never disagree produce a *report*, not a *reconciliation*. Conflict was deferred to VS-04 | **Critical** | Conflict reconciliation is pulled into VS-01 (§A15). The data already contains a genuine one: Sales sees a 90%-probability deal in negotiation; Support sees an active policy escalation with 3 breaching high-priority tickets; DOC-009 records the customer tying the deal to their resolution |
| 2 | **`open_high_priority_count` stated as 4. It is 3.** TKT-073 is high priority but resolved | **Factual error** | Corrected throughout (§A10). Two separate signals: `open_high_priority_count` = 3, `high_priority_total` = 4 |
| 3 | **`as_of` default contradicted the acceptance values.** Default resolves to `max(created_at)` = 2026-08-27, but every asserted value was computed at 2026-09-18. At 2026-08-27 the SLA-breach ranking differs (CUST-009 has 4, CUST-007 has 3) | **Critical** | The acceptance scenario pins `ACCEPTANCE_AS_OF = 2026-09-18` in config. The `max(created_at)` fallback is a convenience for ad-hoc use and is never what the golden file or acceptance run uses |
| 4 | **Assessment uniqueness omitted the Layer 1 snapshot.** Re-running after a new ingestion would hit the unique constraint and silently return stale intelligence | **Critical** | `layer1_fingerprint` is part of the assessment row and of its uniqueness (§A18, §A24) |
| 5 | **Content hash covered the rendered brief.** A whitespace change in a template would invalidate every prior approval | **High** | Approval binds to the **decision payload** (findings, positions, resolution, action, citations), excluding all timestamps and `template_version`. Rendered prose is a view (§A17, §A24) |
| 6 | **Analysts were to receive a SQLAlchemy `Session`.** Scope enforcement would then be advisory — any module holding a session can read any table | **Critical** | Analysts receive **pre-built, typed context objects and never a session** (§A14). Scope becomes a property of construction, not a convention |
| 7 | **Executive-worthiness depended on a derived text link** (`contract_document_present`) | **High** | Worthiness is gated only on `CANONICAL_FK`-backed commercial linkage (active deal or active project). Contract documents are evidence, never a gate (§A15) |
| 8 | **Timezone rule unspecified.** `created_at` is UTC-aware; `as_of` is a date. Naive comparison shifts 14-day window boundaries by one day | **High** | All bucketing uses `created_at.astimezone(UTC).date()`; every window is a closed interval of UTC dates (§A24) |
| 9 | **Derived links had no recomputation trigger.** Documents change; `computed_at` alone leaves links stale | **Medium** | Links are derived inside the assessment run and stamped with `linker_version` + `layer1_fingerprint` (§A18) |
| 10 | **"No outbound import" boundary test was overstated.** The API package already imports HTTP machinery, and the acceptance script needs a client — exactly the situation I1 solved with named exemptions | **Medium** | The test walks the **transitive** import graph of the intelligence/analyst/decision packages and uses the I1 named-exemption mechanism, with each exemption justified and removable (§A22) |
| 11 | Briefs were to be generated for all 50 customers | Low | Assessments for all 50; briefs only for band ≥ `WATCH`. Citation resolution is tested on both |
| 12 | Risk of a speculative generic graph API | Medium | The relationship model exposes exactly the queries of §A9 — **three** after the v2.1 correction below. **No generic `traverse()` in VS-01** |
| 13 | `POST /risk/assessments` re-run semantics undefined | Low | Re-run with an identical fingerprint returns `200` with the existing assessment; a new fingerprint creates a new one (`201`) |
| 14 | Money had no type | Medium | `MoneyValue(amount, currency)` — never summed across currencies. This is the seam VS-02's FX plugs into (§A12) |
| 15 | Acceptance needed a modified corpus for the DOC-005 test, on a stack whose image excludes fixtures | Medium | The leave-one-out test runs in-process against a dedicated test database, not through the deployed stack (§A25) |
| 16 | Multi-currency edge cases untested (one EUR deal exists; some customers hold two currencies) | Low | Named fixtures (§A26) |

---

## 0.1 What v2.1 changed, and why — the M2/M4 boundary

Found while grilling M2 before implementation, on 2026-09-20. Nothing outside these three
documentation points changed, and no code was written.

| # | Contradiction in v2 | Severity | Resolution in v2.1 |
|---|---|---|---|
| 17 | **M2 was specified to build two incompatible things.** Its *Change* bullet said `queries.py` implements "the four queries of §A9", and §A9's third query is `documents_for(customer)` → *derived links with basis, matched token and offsets*. Its *Non-goals* line said "Derived document links (M4)". M2 could not both implement all four §A9 queries and exclude derived document links | **High** | `documents_for()` is **not** a relationship query. It is an M4 evidence interface exported from `app/evidence/`, and §A9 now lists **three** public relationship queries. Seven independent signals in v2 already pointed this way: M4 builds the linker, the link table and the first additive migration; M4's named tests *are* the document-link tests; M4's *Before* reads "Documents are unreachable from a customer", which is false if M2 linked them; M2's test list contains no document assertion; M1's `DerivedLink` requires a `linker_version` that does not exist until M4; and the dependency order says M4 may start once **M1** is done, not M2 |
| 18 | **Source-key joins counted five in §A9 and six in the strategy** (§2.2, §5.1). `project_owned_by` (`projects.owner_source_id`) was the missing one | Low | Both documents now say the same thing: **six exist in Layer 1, five are modelled in VS-01.** `project_owned_by` is not modelled because no §A9 query needs a project's owner |

**Why the boundary is cleaner this way.** Derived links and canonical edges are different kinds of
knowledge — one is a provenance-backed fact, the other an inference carrying a `linker_version`,
a matched token and the evidence a reviewer checks it against. Keeping them behind separate
interfaces, with `app/evidence` reading `app/relationships` and never the reverse, turns §A11's
central rule — *no VS-01 signal is derived from any document link* — into a structural property
of the import graph rather than a rule a reviewer must remember. It also preserves M2's stated
rollback property: M4 adds a package instead of reopening M2's.

---

## Part A — Specification

### A1. Business objective

Detect, with verifiable evidence, when one customer's **service relationship is deteriorating
while commercial pressure is being applied to the same account**, reconcile the opposing
functional views into a single executive recommendation, and place that recommendation in front
of a human for approval.

### A2. Executive question

"Which customers currently require executive attention, why, and what should we do?"

Demonstration instance: *"Why is Meridian Textiles at risk, and what should the CEO do?"*

### A3. Why this slice proves the concept

The AI CEO thesis is that fragmented signals across functions get reconciled into one executive
decision a human approves. A slice where two analysts agree would only demonstrate reporting.
This slice contains a **real conflict, present in the committed data**:

| Function | Reads | Concludes | Wants |
|---|---|---|---|
| Sales | `deals` | DEAL-001 is in `negotiation` at 90% probability and active | `ACCELERATE_DEAL_CLOSE` |
| Support | `support_tickets` + DOC-003 | Policy escalation active (5 tickets in 9 days); 3 open high-priority tickets past SLA resolution target | `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` |

These are incompatible actions on the same object (DEAL-001). DOC-009 records that the customer
*"tied the Meridian Textiles - Seat Expansion decision (DEAL-001) to resolving them"*. The
reconciler must therefore choose, justify the choice against a stated policy, and **preserve the
losing position as recorded dissent**. That is executive reconciliation, achieved
deterministically, with no model.

### A4. Personas

CEO / executive sponsor (decides) · account owner EMP-007 Vikram Pillai (owns the account) ·
Head of Customer Support EMP-004 Karan Kapoor (owns the breaches).

### A5. Definitions — fixed before any code

| Term | Definition |
|---|---|
| **Risk** | Observable deterioration in the service relationship. **Not** churn probability. Ordinal band, never a percentage |
| **Risk band** | `NONE` / `WATCH` / `ELEVATED` / `CRITICAL`, assigned by a versioned decision table in configuration |
| **Policy escalation state** | Boolean. True when three or more tickets fall in **any** 14-day window whose end lies within `lookback_days` of `as_of`. Threshold and window come from DOC-003 via config |
| **SLA resolution-target breach** | Elapsed business days exceed DOC-003's target for the ticket's priority (high 1, medium 5). Resolved: created→resolved. Open: created→`as_of` |
| **Active deterioration** | Ticket velocity in the lookback window plus open high-priority tickets. Drives the band |
| **Chronic backlog** | An open ticket far past target but isolated in time. Reported separately; **never** drives the band |
| **Position** | A function's stance: `{function, stance, proposed_action, rationale, citations}` |
| **Conflict** | Two positions proposing actions declared incompatible over the same object |
| **Executive-worthy** | Band ≥ `ELEVATED` **and** a `CANONICAL_FK`-backed commercial linkage (active deal or active project) |
| **`as_of`** | The evaluation date. Acceptance pins `2026-09-18`. Ad-hoc fallback: `max(support_tickets.created_at)` in scope. **`now()` is forbidden** |
| **Scope** | One `source_system` (default `csv_demo`) plus `as_of` plus `layer1_fingerprint` |
| **`layer1_fingerprint`** | SHA-256 over the scoped canonical `(source_id, record_hash)` pairs and per-entity counts, each entity's list ordered by `source_id`. Identifies the Layer 1 snapshot an assessment was computed from. Composition, exclusions and rationale: §A5.1 |

#### A5.1 `layer1_fingerprint` — composition (decided at M0 closure, 2026-09-19)

**Composition.** SHA-256 over the UTF-8 JSON serialisation of

```
{entity_type: {"count": n, "records": [[source_id, record_hash], ...]}}
```

for the seven canonical entity types within the scope, serialised with the same discipline as
Layer 1's `record_hash` (`sort_keys=True`, `separators=(",", ":")`).

**Ordering rule.** Each `records` list is read with an explicit `ORDER BY source_id`. PostgreSQL
guarantees no row order without one, and a fingerprint computed over unordered rows is not
reproducible.

**Excluded fields.** `ingested_at`, `ingestion_run_id` and `source_updated_at` are deliberately
**not** read. They change on every ingestion, so including them would make an unchanged
re-ingestion mint a new fingerprint — destroying the very idempotency the fingerprint exists to
protect.

**What it detects.** Measured against the clean 233-row demo database:

| Change | Detected |
|---|---|
| Business-content change (a `record_hash` differs) | yes |
| `source_id` rename that reorders the sequence | yes |
| `source_id` rename that **preserves** ordinal position (`CUST-007` → `CUST-007Z`) | yes |
| `source_id` addition | yes |
| `source_id` removal | yes |

**Why `source_id` must be included.** Layer 1's `record_hash` covers business fields only and
**excludes all provenance, including `source_id`** (`app/normalization/contract.py`). A
composition over `record_hash` values and counts alone is therefore blind to every `source_id`
rename — yet `source_id` is the join key for every `SOURCE_KEY_JOIN` edge, the input to
`canonical_id`, what E1 resolves the three customer FKs against, and the token quoted in
`ID_TOKEN` document links and brief citations. A rename re-keys rows, re-resolves FKs and
invalidates citations while leaving every `record_hash` untouched.

**Layer 1 stays frozen.** This is a **Layer 2 composition over two frozen Layer 1 columns**. It
requires no change to `record_hash`, no change to any Layer 1 module, no migration and no D1
vocabulary change.

**Determinism requirement.** The fingerprint must be byte-identical across independent clean
rebuilds of the database. Verified at M0 closure: two independently built databases (different
run ids, different `ingested_at` values) both yielded
`1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00` for
`source_system='csv_demo'` over the committed demo dataset.

### A6. End-to-end workflow

```
  operator / API caller
        │  as_of, source_system, [customer]
        ▼
  1. Scope resolution      source_system + as_of + layer1_fingerprint
        ▼
  2. Relationship model    customer neighbourhood; every edge carries its basis
        ▼
  3. Signal engine         S1..S15 computed as of the scope date
        ▼
  4. Risk band             decision table  →  band + satisfied rule ids
        ▼
  5. Evidence              derived customer↔document links + structural policy citations
        ▼
  6. Analyst contexts      two disjoint, pre-built context objects (no DB session)
        ▼
  7. Positions             SupportRiskAnalyst  →  Position(support)
                           CommercialAnalyst   →  Position(sales)
        ▼
  8. Conflict detection    incompatible proposed actions over the same object?
        ▼
  9. Reconciliation        versioned conflict policy → resolved action + preserved dissent
        ▼
 10. Brief                 decision payload (hashed) + rendered narrative (a view)
        ▼
 11. Human decision        APPROVED / REJECTED bound to the payload hash
        ▼
  (no executor exists)
```

### A7. Trigger and inputs

Explicit only. `POST /api/v1/risk/assessments` or `make verify-vs01`. No scheduler, no worker.
Inputs: `as_of: date | None`, `source_system: str = "csv_demo"`,
`customer_source_id: str | None`, plus `lookback_days`, `rules_version`, `policy_version`,
`linker_version` from configuration.

### A8. Layer 1 contracts consumed (unchanged)

`customers`, `support_tickets`, `deals`, `projects`, `employees`, `documents`, read in-process
through the existing repository layer. **VS-01 requires no Layer 1 contract extension.**

### A9. Relationship model

Nodes: `Customer`, `SupportTicket`, `Deal`, `Project`, `Employee`, `Document`.

| Edge | Basis | Produced by |
|---|---|---|
| `customer_has_ticket` / `customer_has_deal` / `customer_has_project` | `CANONICAL_FK` | M2 |
| `customer_owned_by`, `ticket_assigned_to`, `deal_owned_by`, `employee_reports_to`, `document_owned_by` | `SOURCE_KEY_JOIN` (within one source system) | M2 |
| `document_mentions_customer` | `DERIVED_TEXT_MATCH` (id token or exact full name) | **M4** |
| `document_relates_to_topic` | `DERIVED_TOPIC_MATCH` — supporting evidence only | **M4** |

The first two rows are the **relationship model** (M2). The last two are **derived links** (M4)
and are reached through the evidence interface below, never through the relationship API. The
`EdgeBasis` vocabulary that names all four is M1's and is not redeclared.

**Source-key joins: six exist in Layer 1, five are modelled in VS-01.** Strategy §2.2 inventories
six source-key relationships; row two models five of them. `project_owned_by`
(`projects.owner_source_id`) is deliberately **not** modelled: no query below needs a project's
owner, and an edge no query asks for is an edge built on speculation — the failure mode §4 of the
strategy gives as the reason for building slices instead of a horizontal graph. VS-02 adds it when
pipeline ownership acquires a consumer.

**Exactly three public relationship queries. No generic traversal API in VS-01.**

1. `neighbourhood(customer)` → tickets, deals, projects, account owner
2. `escalation_path(customer)` → account owner → manager, plus each open ticket's assignee → manager
3. `policy_documents()` → `document_type = 'policy'`

**Derived document links are not a fourth relationship query.** `documents_for(customer)` →
derived links with basis, matched token and offsets — is an **M4 evidence interface** exported
from `app/evidence/`, outside the M2 relationship API (§A11).

The dependency runs one way: `app/evidence` reads `app/relationships`, never the reverse. That
is what makes §A11's rule — *no VS-01 signal is derived from any document link* — **structural
rather than advisory**. The M3 signal engine is built against the relationship API, so it cannot
reach a derived link at all; enforcement does not rest on a reviewer remembering the rule. It
also keeps the two kinds of knowledge from being confused at the call site: a `CANONICAL_FK`
edge is a provenance-backed fact, whereas a `DERIVED_TEXT_MATCH` link is an inference carrying
`linker_version`, its matched token and the evidence a reviewer checks it against.

### A10. Signals (deterministic, computed at `as_of`)

| # | Signal | Band input? | CUST-007 @ 2026-09-18 |
|---|---|---|---|
| S1 | `open_ticket_count` | yes | **4** |
| S2 | `open_high_priority_count` | yes | **3** (TKT-075, 076, 080) |
| S2b | `high_priority_total` | context | **4** (S2 + resolved TKT-073) |
| S3 | `tickets_in_lookback` | yes | 5 |
| S4 | `max_tickets_in_14d_window` | yes | 5 (2026-08-18 → 08-31) |
| S5 | `policy_escalation_state` | yes | **true** |
| S6 | `days_since_last_ticket` | yes | 22 |
| S7 | `sla_breach_count` | context | 5 |
| S8 | `open_sla_breach_high_count` | yes | 3 |
| S9 | `stale_open_ticket_count` | **no** — chronic backlog | 0 |
| S10 | `dominant_ticket_category` | context | `performance` (3/5) |
| S11 | `active_deal_count` + stages + probabilities | worthiness | 1 — negotiation, 90% |
| S12 | `exposure_by_currency` | **no** | `{USD: [DEAL-001, 5361.44, 90%]}` |
| S13 | `active_project_count` | worthiness | **0** |
| S14 | `contract_documents` | evidence only | DOC-006 |
| S15 | `deal_under_pressure` | conflict input | true — an active `negotiation` deal exists while S5 is true |

### A11. Derived document links

**Owned by M4, not M2.** These links are produced by `app/evidence/linker.py` and read through
`documents_for(customer)`, which `app/evidence/` exports. They are not edges of the M2
relationship API (§A9), and Layer 1's `documents` table gains no customer reference to hold them.

| Basis | Rule | May derive signals? | CUST-007 |
|---|---|---|---|
| `ID_TOKEN` | Canonical `source_id` appears as a whole token in title or body | Yes | DOC-005, DOC-006, DOC-009 |
| `EXACT_NAME` | Full customer name, case-insensitive, at token boundaries | Yes | DOC-006, DOC-009 |
| `TOPIC` | Document topic overlaps the dominant ticket category | **No** | DOC-010 (supporting only) |

Substring matching is **forbidden** and pinned by a test: the dataset holds "Meridian Textiles",
"Westbrook Textiles", "Northstar Textiles" and "Evergrid Textiles" (CUST-039).

**In VS-01 no signal is derived from any document link.** Every signal S1–S15 is computed
deterministically from canonical `support_tickets`, `deals` and `projects` rows; S14
(`contract_documents`) is evidence only. The "may derive signals" column above is a property
reserved for later slices. This matters because DOC-005 is an `ID_TOKEN` match for CUST-007 and
states the escalation conclusion in prose, so §A25 test 4 must keep asserting exact equality of
**every signal value** — that test is what stops a later slice from quietly making the conclusion
document-derived.

The same reasoning fixes the boundary in §A9: because `documents_for()` sits outside the
relationship API that M3 is built against, "no signal is derived from a document link" is enforced
by what the signal engine can import, not only by §A25 test 4. The test remains the second line of
defence, not the first.

### A12. Money

`MoneyValue(amount: Decimal, currency: str)`. Rendering is always currency-qualified. **Summing
across currencies raises.** No total pipeline figure exists in VS-01. This type is the seam
VS-02's FX normalization plugs into without touching VS-01's call sites.

### A13. ML and retrieval

No model. No embeddings. No vector store. No prompt. Evidence selection is deterministic; policy
citations are structural, because the rule configuration names its source document (DOC-003).

### A14. Analyst contract — data in, position out

Each analyst is constructed with a **pre-built, typed context object and is never given a
database session**. Scope is therefore enforced by construction, not by convention.

| Analyst | Context contains | Context cannot contain | Emits |
|---|---|---|---|
| `SupportRiskAnalyst` | Tickets, SLA rules, policy documents, S1–S10 | Any deal, project or monetary field | `Position(function=SUPPORT)` + band + satisfied rules + breaches |
| `CommercialAnalyst` | Deals, projects, contract documents, S11–S15 | Any ticket record | `Position(function=SALES)` + per-currency exposure + contract terms |

A test asserts each context dataclass has no field of a forbidden type, and that neither analyst
module imports `Session` or any ORM model.

### A15. Conflict detection and reconciliation — the core of the slice

**Detection.** Two positions conflict when they propose actions declared incompatible in
`config/intelligence/conflict_policy.yaml` over the same object identity (here `DEAL-001`).

**Resolution.** A versioned policy entry, for example:

```yaml
version: 1
conflicts:
  - id: CONF-001
    between: [ACCELERATE_DEAL_CLOSE, PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED]
    scope: same_deal
    resolve_to: PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
    when:
      support_band_at_least: ELEVATED
      open_sla_breach_high_count_at_least: 1
    because_documents: [DOC-003, DOC-009]
    rationale: >
      An active support-policy escalation outranks deal acceleration on the same
      account, and the customer has explicitly linked the deal decision to
      resolution of the open tickets.
```

**Dissent is preserved.** The losing position is carried into the brief with its own citations
and is never averaged away or deleted. An executive can see exactly what Sales wanted and why it
did not prevail.

**Worthiness.** Band ≥ `ELEVATED` **and** (`S11 > 0` or `S13 > 0`). Derived document links never
gate worthiness.

**Ordering.** band desc → `S8` desc → `S4` desc → `source_id` asc. **Money is never a sort key.**

### A16. Action catalogue (versioned config)

| Action | Preconditions | Proposed by |
|---|---|---|
| `ESCALATE_TO_ACCOUNT_OWNER_PER_SLA` | `S5` | Support |
| `SCHEDULE_EXECUTIVE_SPONSOR_CALL` | `S5` and `S11 > 0` | Support |
| `ASSIGN_DEDICATED_SUPPORT_OWNER` | `S8 >= 2` | Support |
| `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` | `S8 >= 1` and an active `negotiation` deal | Support |
| `REVIEW_INVOICE_DISPUTE` | an open `billing` ticket | Support |
| `ACCELERATE_DEAL_CLOSE` | active deal, stage `negotiation`, probability ≥ 80 | Sales |
| `NO_ACTION` | band `NONE` | — |

At the pinned `as_of`, CUST-007 triggers all six non-`NO_ACTION` entries, and the last two
conflict.

### A17. Brief — payload and view, separated

- **Decision payload (hashed, binding):** customer identity, band, satisfied rule ids, signal
  values, both positions, the detected conflict, the resolution and its policy id, the resolved
  action set, and every citation. Excludes all timestamps and `template_version`.
- **Rendered narrative (a view, not hashed):** sections for identity · risk state and why ·
  evidence · commercial context (per currency) · **conflict and how it was resolved** ·
  **recorded dissent** · policy and contract context · chronic backlog · recommended actions ·
  escalation path · limitations.

**Evidence contract:** every asserted fact carries `{kind: "record", entity, id, field}` or
`{kind: "document", document_id, start, end}`. An unresolvable citation makes the brief invalid
and the generator raises.

**Absence is stated, never omitted.** CUST-007 has no active project; the brief says so.

### A18. Persistence — new tables only, additive revision from `8bfd73b6af60`

| Table | Key columns |
|---|---|
| `document_customer_links` | `document_id` FK, `customer_id` FK, `basis`, `matched_token`, `match_start`, `match_end`, `linker_version`, `layer1_fingerprint` |
| `risk_assessments` | `customer_id` FK, `as_of`, `source_system`, `layer1_fingerprint`, `rules_version`, `band`, `satisfied_rules` JSONB, `signals` JSONB, `executive_worthy`; **unique** `(customer_id, as_of, source_system, layer1_fingerprint, rules_version)` |
| `risk_positions` | `assessment_id` FK, `function`, `stance`, `proposed_action`, `rationale`, `citations` JSONB |
| `risk_briefs` | `assessment_id` FK, `policy_version`, `template_version`, `decision_payload` JSONB, `payload_hash`, `narrative` TEXT, `status` `DRAFT`; **unique** `(assessment_id, payload_hash)` |
| `brief_decisions` | `brief_id` FK, `payload_hash`, `actor`, `decision`, `note`, `decided_at`, `supersedes_id` nullable. **Append-only** |

Canonical tables are untouched; downgrade drops only these five.

### A19. API (additive; F1/F2 conventions reused unchanged)

| Route | Method | Notes |
|---|---|---|
| `/api/v1/risk/assessments` | POST | `201` for a new fingerprint; `200` returning the existing assessment for a repeat |
| `/api/v1/risk/assessments` | GET | filter by `as_of`, band, `executive_worthy`; limit/offset |
| `/api/v1/risk/assessments/{id}` | GET | signals, satisfied rules, positions |
| `/api/v1/risk/briefs/{id}` | GET | payload + narrative + citations |
| `/api/v1/risk/briefs/{id}/decision` | POST | body carries `actor`, `decision`, `note`, `payload_hash`; mismatch → conflict error |
| `/api/v1/risk/briefs/{id}/decisions` | GET | decision history |

### A20. UI

None. OpenAPI `/docs` only, as in Layer 1.

### A21. Observability

`log_event` + existing counters. Events: `vs01.scope_resolved` (as_of, fingerprint, resolution
path) · `vs01.signals_computed` · `vs01.band_assigned` · `vs01.links_derived` ·
`vs01.conflict_detected` (policy id) · `vs01.conflict_resolved` (winning action) ·
`vs01.brief_generated` (payload hash, citation count) · `vs01.decision_recorded`. No document
text, customer email or monetary value in any log line.

### A22. Security

| Concern | Control |
|---|---|
| Prompt injection | **Structurally impossible** — no model, no prompt. A named reason for the templated design |
| Document text as instruction | Rendered only as quoted, length-capped, escaped evidence with id and span. The linker never treats body text as configuration |
| Customer-scope leakage | A brief for X contains no other customer's identifiers — tested |
| Analyst scope | Enforced by construction (§A14), not by convention |
| No executor | Static test over the **transitive** import graph of `app/intelligence`, `app/relationships`, `app/evidence`, `app/analysts`, `app/decisions`: no outbound HTTP/SMTP/source-write path. The same test pins the §A9 dependency direction — `app/relationships` must not import `app/evidence`. Named exemptions use the I1 mechanism, each justified, and a test removes an exemption that is no longer needed |
| Approver identity | Recorded but **asserted, not verified** — there is no authentication. A documented prerequisite for any future executor |

### A23. Failure modes

Ticketless customer → band `NONE`, not an error (15 such customers — 11 active, plus all 4 inactive ones, which are a subset).
NULL `customer_id` FK → excluded from signals **and** reported as a `data_quality` note, never
silently dropped. Empty database → empty result. `as_of` before all data → all `NONE`, scope
reported empty. `as_of` in the future → permitted, recency decays. Invalid rules or policy config
→ refuse at load naming the broken rule; no partial assessment. NULL `body_text` → linker skips.
Stale `payload_hash` on a decision → conflict error. Concurrent identical assessments → unique
constraint makes the second a read.

### A24. Determinism and idempotency

- An assessment is a pure function of (`as_of`, `source_system`, `layer1_fingerprint`,
  `rules_version`, `policy_version`, `linker_version`).
- **Date rule:** bucket by `created_at.astimezone(UTC).date()`; every window is a closed interval
  of UTC dates. Business-day arithmetic uses a fixed weekday rule with **no holiday calendar** —
  a stated limitation.
- `payload_hash` uses the same serialisation discipline as `record_hash` (sorted keys, compact
  separators, normalised `Decimal`, UTC ISO-8601) over the decision payload with timestamps and
  `template_version` excluded.
- No `now()`, no randomness, no dict-ordering or locale dependence.

### A25. Evaluation

| Layer | Proves |
|---|---|
| Unit | Every signal against hand-computed values; band table; catalogue preconditions; conflict detection and resolution; link bases; business-day and UTC-window arithmetic; hash stability |
| Contract | Analyst context purity; evidence-contract validity; API shapes from OpenAPI |
| Integration | Migration up/down; uniqueness incl. fingerprint; append-only decisions; hash conflict; idempotent re-run |
| End-to-end | assess → brief → approve over HTTP; reject path |
| Acceptance | `make verify-vs01` — named checks, each with a pass condition and a line of observed evidence, in the `verify_layer1.py` style |

**Named tests**

1. **Single-escalation.** At the pinned `as_of`, CUST-007 is the only customer with `S5` true and the only `CRITICAL` one.
2. **Conflict.** Both positions are produced; the conflict is detected; `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` wins; `ACCELERATE_DEAL_CLOSE` is preserved as dissent with its citations.
3. **Conflict-policy liveness.** Flipping `resolve_to` flips the outcome — the policy is load-bearing, not decorative.
4. **DOC-005 leave-out.** With DOC-005 removed, band, every signal, the escalation state and the resolution are byte-identical. Runs **in-process against a dedicated test database**, not the deployed stack.
5. **Amount invariance.** Multiply every deal amount by 1000 — the ranking does not change.
6. **Chronic backlog.** CUST-048 and CUST-009 do not outrank CUST-007; their stale tickets appear as backlog observations, not escalation drivers.
7. **Substring safety.** Westbrook, Northstar and Evergrid Textiles acquire no Meridian link.
8. **Citation resolution.** Every citation in every assessment and every generated brief resolves.
9. **Scope leakage.** No brief contains another customer's `source_id`, name or email.
10. **Negative cases.** The 15 ticketless customers, which include all 4 inactive ones, yield `NONE`, not worthy.
11. **Rule liveness.** Escalation threshold 3 → 6 makes CUST-007 non-escalated.
12. **Determinism.** Two runs in separate processes give identical `payload_hash`; re-run inserts nothing.
13. **Fingerprint sensitivity — content and count.** Ingesting one extra ticket changes the fingerprint and produces a **new** assessment rather than returning the stale one.
13b. **Fingerprint sensitivity — identity.** Re-ingest one record under a changed `source_id` whose sort position is unchanged (e.g. `CUST-007` → `CUST-007Z`) with byte-identical business content. The fingerprint **must** change. Test 13 alone cannot catch this, because `record_hash` excludes `source_id` (§A5.1).
14. **Multi-currency.** A customer with USD and INR deals renders both, and any attempt to sum them raises.

Mutation testing uses the project's existing ad-hoc textual harness over the signal engine, the
band table, the conflict policy and the linker.

### A26. Fixtures

No change to `data/demo/`. New fixtures only: corpus without DOC-005; deals with scaled amounts;
documents with a customer name embedded as a substring of another; a ticket with an unresolved
`customer_source_id`; a customer holding deals in two currencies; a document containing
instruction-like text, asserted to be quoted and never interpreted.

### A27. Acceptance criteria (binary)

1. `make verify-vs01` exits 0 against a running stack whose database was built by the **clean full-dataset path** (§A28): all 233 canonical rows across all 7 entity types, evaluated at `ACCEPTANCE_AS_OF = 2026-09-18`.
1b. The computed `layer1_fingerprint` equals the value pinned in `config/intelligence/risk_rules.yaml`. A mismatch fails the run with a named message rather than producing an assessment. This is what stops a `make verify-layer1` residue — which ingests only 5 of 7 entity types and injects malformed-fixture rows into the `csv_demo` scope — from silently yielding a citation-free brief.
2. Exactly one customer is `CRITICAL` and executive-worthy: CUST-007.
3. Its brief cites, each resolvably: 5 tickets in a 9-day span; 4 open; **3 open high-priority**; 4 high-priority in total; 3 open high-priority SLA breaches; dominant category `performance`; DEAL-001 `negotiation` at 90% for **USD** 5,361.44; DOC-003's escalation rule; DOC-006's 36-month term and 90-day notice; DOC-009's linkage of the deal to ticket resolution.
4. The brief states that CUST-007 has no active project.
5. The brief contains a detected conflict, a named resolution policy, the winning action and the recorded dissent.
6. Every citation across all assessments and briefs resolves.
7. Tests 1–14 of §A25 pass.
8. Two runs give an identical `payload_hash` and insert no rows; changing the Layer 1 snapshot produces a new assessment.
9. Approval writes one decision row; a second on the same hash is refused without `supersedes_id`; rejection is recorded; nothing is executable.
10. Regression: full Layer 1 suite passes unchanged; `app/` coverage stays 100%; ruff 69; mypy 9; secret scan 0.

### A28. Demo (~5 minutes, no network, no key, no model)

> **Evaluation-state prerequisite.** The database must come from the clean full-dataset path:
> an empty database → `make migrate` → `make ingest-demo` with **no `--entities` filter** →
> 233 rows over 7 entity types, 0 rejected, `SUCCESS`; a repeat run is `NOOP`.
> **Do not use `make verify-layer1` to prepare a VS-01 evaluation database**: by design it
> ingests only the five entity types of spec Section 20 step E (no `organizations`, no
> `documents`) and then ingests the malformed fixture through the `csv_demo` connector, so its
> residue has no documents and four extra rows inside the default scope. It remains the correct,
> unchanged **Layer 1** acceptance command.

`make docker-up && make migrate && make ingest-demo` → `POST /risk/assessments {"as_of":"2026-09-18"}` →
`GET /risk/assessments?executive_worthy=true` (one row) → `GET /risk/briefs/{id}` (read the
conflict and the dissent) → open DOC-003 and DOC-009 at the cited spans and verify two citations
by hand → `POST .../decision {"decision":"REJECTED"}` → `GET .../decisions` → re-run the
assessment (identical hash, no new rows) → `pytest -k doc005_leave_out`.

### A29. Known limitations

Single source system; no cross-source entity resolution; document links derived, not
provenance-backed; `TOPIC` links are supporting only; no FX, so no cross-currency total;
business days have no holiday calendar; the band is a policy artefact, not a probability;
approver identity is asserted, not authenticated; the dataset is synthetic, 233 rows;
`employees.organization_id` remains NULL.

### A30. Reusable foundations this slice establishes

| Foundation | First consumer after VS-01 |
|---|---|
| `Scope` (`as_of`, `source_system`, `layer1_fingerprint`) | every slice |
| Relationship model with per-edge basis | VS-02, VS-03, VS-04, VS-05 |
| `Evidence` / `Citation` contract | every slice |
| `AnalystContext` → `Position` (data in, no session) | VS-04, VS-05 |
| `ConflictPolicy` + reconciler | VS-04 |
| `ActionCatalogue` | VS-03, VS-04 |
| `DecisionRecord` bound to a payload hash | VS-03, VS-04 |
| `MoneyValue` (currency-qualified, never summed) | VS-02 (FX plugs in here) |

### A31. Out of scope

Churn probability; forecasting; Neo4j; embeddings; any language model; multi-source aggregation;
cross-currency totals; scheduling; notification; authentication; any executor; a frontend;
changes to `data/demo/`; changes to any Layer 1 module's behaviour.

---

## Part B — Milestones M1–M9

One commit per milestone, verified before the next begins. **Frozen throughout:** D1/D2
semantics, E1 persistence and status semantics, F1/F2 route contracts, G1 logging and metric
semantics, G2 security behaviour, the H test layers, the I acceptance command, and `data/demo/`.

M0 remains a pre-flight step, not a milestone: record the baselines (suite count, coverage, ruff,
mypy, secret scan) and establish the clean evaluation database via §A28's prerequisite —
an empty database, `make migrate`, then `make ingest-demo` with no `--entities` filter.
**Completed 2026-09-19**; see `CONTEXT/M0_BASELINE_REPORT.md` and `CONTEXT/M0_CLOSURE_REPORT.md`.

---

### M1 — Foundations and contracts

**Objective.** Create the vocabulary and the invariants every later milestone depends on, so that
no later milestone can violate them by accident.

**Before.** Only Layer 1 exists. There is no notion of `as_of`, evidence or money.

**Change.**
- `app/intelligence/contract.py` — `RiskBand`, `EdgeBasis`, `LinkBasis`, `Function`, `Stance`,
  `ActionId`, `SignalSet`, `Citation`, `Evidence`, `Position`, `ConflictResolution`.
- `app/intelligence/scope.py` — `Scope(as_of, source_system, layer1_fingerprint)` and
  `resolve_scope()`, which records which path produced `as_of` and computes the fingerprint
  exactly as §A5.1 defines it: over the scoped canonical `(source_id, record_hash)` pairs and
  per-entity counts, each list read with an explicit `ORDER BY source_id`, excluding
  `ingested_at`, `ingestion_run_id` and `source_updated_at`.
- `app/intelligence/money.py` — `MoneyValue`, whose `__add__` raises across currencies.
- `app/intelligence/timeutil.py` — UTC bucketing and business-day arithmetic.
- `config/intelligence/risk_rules.yaml` — skeleton with `rules_version` and `ACCEPTANCE_AS_OF`.

**Tests.** `as_of` resolution order and the empty-database fallback; fingerprint changes when a
record's business content changes, changes when a `source_id` is renamed **without** changing its
sort position, changes on a `source_id` addition or removal, and is stable when nothing changes;
`MoneyValue` addition raises across currencies; business-day arithmetic across weekends; UTC bucketing at a 23:30 UTC timestamp;
**boundary test** that no module under `app/intelligence/` references `datetime.now`,
`date.today` or `utcnow`.

**After.** `as_of`, money and evidence exist as types, and `now()` is mechanically impossible.

**Acceptance.** Scope resolves against the demo database; the boundary test fails if `now()` is
introduced; the fingerprint is stable across two processes and byte-identical across two
independent clean rebuilds. For the committed demo dataset at `source_system='csv_demo'` it is
`1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00`, which M1 pins in
`config/intelligence/risk_rules.yaml` (§A27.1b).

**Rollback.** Delete the package — nothing depends on it yet.

**Non-goals.** Signals, persistence, API, anything that reads a ticket.

---

### M2 — Relationship model

**Objective.** One uniform way to ask what a customer is connected to, where every edge states
*how it is known*.

**Before.** Relationships exist as three FKs and six loose `source_id` strings, five of which
VS-01 models (§A9).

**Change.** `app/relationships/edges.py` (edge types and basis), `app/relationships/queries.py`
(the **three** relationship queries of §A9 — `neighbourhood`, `escalation_path`,
`policy_documents`), `app/relationships/model.py` (assembly). Read-only; the caller owns
the session, matching the existing repository convention. The package produces `CANONICAL_FK` and
`SOURCE_KEY_JOIN` edges only; it constructs no `DerivedLink` and imports nothing from
`app/evidence/`.

**Tests.** Each edge type resolves on the demo dataset; a `SOURCE_KEY_JOIN` never crosses
`source_system`; a NULL FK yields no edge rather than an error;
`escalation_path(CUST-007)` returns EMP-007 → EMP-002 plus **all four** open-ticket assignees EMP-017/018/020/021 → EMP-004 (§A9 says *each open ticket's* assignee, so EMP-017 is included for the open `medium` billing ticket TKT-079; it must not be filtered to high priority);
`neighbourhood(CUST-007)` returns 5 tickets, 1 deal, **0 projects**; a test asserts **no public
`traverse()`** exists.

**After.** Every later milestone reads relationships through one interface instead of ad-hoc
joins.

**Acceptance.** The three queries return the measured neighbourhoods; every returned edge carries
a basis.

**Non-goals.** Derived document links and `documents_for()` — both M4 (§A9, §A11); any graph
database; generic traversal; `project_owned_by` (§A9).

---

### M3 — Signal engine and risk band

**Objective.** Turn the neighbourhood into S1–S15 and an explainable band.

**Before.** Relationships are queryable but nothing is measured.

**Change.** `app/intelligence/signals.py` (S1–S15), `app/intelligence/windows.py` (the 14-day
sliding window and the lookback constraint), `app/intelligence/bands.py` (decision table
evaluation returning band **plus the satisfied rule ids**), and the populated
`config/intelligence/risk_rules.yaml`.

**Tests.** Every signal hand-computed for CUST-007, CUST-009, CUST-048, a ticketless customer and
an inactive one; **S2 = 3 and S2b = 4** pinned explicitly, because v1 got this wrong; sliding
window at 13/14/15-day boundaries; `as_of` sensitivity documented by a test at both 2026-08-27
and 2026-09-18; every row of the band table; rule liveness (threshold 3 → 6); amount invariance;
chronic backlog separation.

**After.** Risk is measured and every band assignment carries its reasons.

**Acceptance.** CUST-007 is the only escalated and only `CRITICAL` customer at
`ACCEPTANCE_AS_OF`; CUST-048 and CUST-009 rank below it with their stale tickets reported as
backlog.

**Non-goals.** Documents, persistence, positions, briefs.

---

### M4 — Evidence and citations

**Objective.** Make every future claim checkable, and link documents to customers without
touching Layer 1.

**Before.** Documents are unreachable from a customer.

**Change.** `app/evidence/linker.py` (`ID_TOKEN`, `EXACT_NAME`, `TOPIC`),
`app/evidence/documents.py` exporting **`documents_for(customer)`** — the evidence interface
§A9 keeps out of the M2 relationship API — `app/evidence/citations.py` (build and resolve),
`app/persistence/models/document_customer_link.py`,
its repository, and the **first additive Alembic revision** (`document_customer_links`) branching
from `8bfd73b6af60`. Links are derived inside an assessment run and stamped with `linker_version`
and `layer1_fingerprint`.

`app/evidence/` may read `app/relationships/`; the reverse import is forbidden and §A22's boundary
test pins the direction. M4 therefore **adds a package** rather than reopening M2's, and M2's
"rollback = delete the package" property survives M4.

**Tests.** `documents_for(CUST-007)` returns exactly the links below and nothing else — DOC-010
carries neither the `CUST-007` token nor the name, so it is reachable only as a `TOPIC` link and
never as a customer association; id-token matching finds DOC-005/006/009 for CUST-007;
exact-name finds DOC-006/009;
substring safety across the three "… Textiles" customers; NULL `body_text` skipped; spans resolve
to the exact quoted text; record citations resolve to a real field; an adversarial document is
quoted, never interpreted; downgrade drops only the new table.

**After.** Any claim can cite a record field or a document span, and the citation is verifiable.

**Acceptance.** Links reproduce the measured expectation; every citation resolves.

**Non-goals.** Embeddings; letting `TOPIC` links derive signals; exposing `documents_for()` through
`app/relationships/` (§A9); adding any customer reference to Layer 1's `documents` table.

---

### M5 — Analysts and positions

**Objective.** Split the enterprise view into two disjoint functional views that cannot see each
other's data, and have each state a position.

**Before.** All facts sit in one undifferentiated bag.

**Change.** `app/analysts/context.py` (`SupportContext`, `CommercialContext` — plain dataclasses
built by a factory; **no session, no ORM model**), `app/analysts/base.py`,
`app/analysts/support_risk.py`, `app/analysts/commercial.py`. Each emits a `Position` with a
proposed action drawn from the catalogue and citations for every claim.

**Tests.** A context-purity test asserting `SupportContext` has no deal/project/monetary field
and `CommercialContext` has no ticket field; an import test asserting neither analyst module
imports `Session` or an ORM model; each `Position` validates and carries citations; exposure is
per currency and summing raises; Support proposes `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` and
Sales proposes `ACCELERATE_DEAL_CLOSE` for CUST-007.

**After.** Two functions reason independently, and their isolation is structural.

**Acceptance.** Both positions are produced for CUST-007 with the expected opposing actions;
scope violations are impossible to express, not merely discouraged.

**Non-goals.** Reconciliation; any model; persistence.

---

### M6 — Conflict detection and reconciliation

**Objective.** **The heart of the slice.** Detect that two functions want incompatible things,
resolve it by a stated policy, and keep the losing argument.

**Before.** Two positions exist side by side with nothing deciding between them.

**Change.** `app/decisions/conflicts.py` (detection over proposed actions and object identity),
`app/decisions/policy.py` (load and evaluate `conflict_policy.yaml`),
`app/decisions/reconciler.py` (worthiness, ordering, resolved action set, dissent),
`config/intelligence/conflict_policy.yaml`, `config/intelligence/action_catalogue.yaml`.

**Tests.** Conflict detected for CUST-007 over DEAL-001; `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED`
wins; the resolution cites DOC-003 and DOC-009; **dissent is preserved with its own citations**;
policy liveness — flipping `resolve_to` flips the outcome; a customer with no deal produces no
conflict and no dissent; worthiness truth table; ordering unchanged when amounts are perturbed;
an unresolvable conflict (no matching policy entry) raises rather than silently picking one.

**After.** The system performs executive reconciliation, deterministically and explainably. This
is the milestone that makes the slice a proof of the AI CEO concept rather than a report.

**Acceptance.** For CUST-007 the conflict, the winning action, the named policy id and the
recorded dissent are all present and correct.

**Non-goals.** More than two functions (VS-04); model-generated rationale.

---

### M7 — Brief assembly, hashing and persistence

**Objective.** Freeze a decision into something that can be shown to a human and bound to an
approval.

**Before.** A reconciled result exists only in memory.

**Change.** `app/decisions/payload.py` (the hashed decision payload), `app/decisions/brief.py`
(narrative rendering), `app/decisions/templates/`, models for `risk_assessments`,
`risk_positions` and `risk_briefs`, their repositories, and the **second additive migration**.

**Tests.** Payload hash excludes timestamps and `template_version` — changing a template does
**not** change the hash, changing a fact **does**; hash identical across two processes;
uniqueness including `layer1_fingerprint`; **fingerprint sensitivity** — one extra ingested
ticket yields a new assessment rather than the stale one; re-run inserts nothing; absence stated
(CUST-007 has no project); citation resolution across every generated brief; the **DOC-005
leave-out test** in-process against a dedicated test database; a golden file for the CUST-007
brief at `ACCEPTANCE_AS_OF`.

**After.** A brief is reproducible, diffable and approvable.

**Acceptance.** The CUST-007 brief matches the golden file byte-for-byte and contains every item
of §A27.3 and §A27.5.

**Non-goals.** Approval; API; UI.

---

### M8 — API and the human approval boundary

**Objective.** Expose the slice over the existing API contract, and make the governance boundary
real and unbypassable.

**Before.** The slice is reachable only from Python.

**Change.** `app/decisions/approval.py` (append-only decisions bound to `payload_hash`), the
`brief_decisions` model and **third additive migration**, `app/api/v1/risk.py` (six routes),
additions to `app/api/v1/schemas.py`, router registration.

**Tests.** Append-only — an update attempt fails; a stale `payload_hash` is refused; a second
decision requires `supersedes_id`; rejection is recorded; OpenAPI-discovered contract tests in
the H4 style; `POST` re-run returns `200` with the existing assessment; error bodies leak no
document text or email; **the transitive no-executor boundary test** over all four packages,
with named, justified exemptions; existing F1/F2 contract tests still pass unchanged.

**After.** A human can approve or reject, the record is permanent, and the system provably cannot
act on it.

**Acceptance.** A rejected brief is recorded and nothing is executable; the boundary test fails
if an outbound client is introduced anywhere in the transitive graph.

**Non-goals.** Authentication (documented as a prerequisite for any future executor); execution;
a frontend.

---

### M9 — Acceptance, evaluation and hardening

**Objective.** Make the whole slice a single reproducible command, and prove the claims rather
than asserting them.

**Before.** The pieces work; the scenario is not executable end to end.

**Change.** `scripts/vs01_acceptance.py` and `make verify-vs01` (named checks, each with a pass
condition and one line of observed evidence, in the `verify_layer1.py` style);
`tests/e2e/test_vs01_scenario.py`; the fixtures of §A26; a README section; a VS-01 phase record
appended to `CONTEXT/AI_CEO_PROJECT_CONTEXT.md`; a mutation audit over the signal engine, band
table, conflict policy and linker.

**Tests.** The full §A28 flow over HTTP; all fourteen named tests of §A25; the Layer 1 regression
groups; baseline checks for ruff, mypy, coverage and secret scan.

**After.** VS-01 is demonstrable, reproducible by a reviewer, and its foundations (§A30) are ready
for VS-02.

**Acceptance.** All ten criteria of §A27.

**Non-goals.** Starting VS-02; generalising any slice-local component before its second consumer
exists.

---

### Dependency order

`M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9`

M2 and M3 may overlap; M4 may start once M1 is done — it adds `app/evidence/` rather than
reopening `app/relationships/`, which is why it does not depend on M2 (§A9, §0.1 defect 17).
Every other edge is a hard dependency.
M6 is the milestone that must not be cut — without it the slice is a report, not a proof.
