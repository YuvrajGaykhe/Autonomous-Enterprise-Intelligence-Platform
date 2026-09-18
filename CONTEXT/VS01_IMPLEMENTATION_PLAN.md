# VS-01 — Customer Risk & Executive Escalation: Implementation Plan
**Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
**Created: 2026-09-18 | Maintained by: Yuvraj Gaykhe**
**Status: PLANNED. Nothing in this document is implemented. Do not begin until approved.**

> Strategy context: `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md`
> Layer 1 state: `CONTEXT/AI_CEO_PROJECT_CONTEXT.md`
>
> **Layer 1 is frozen.** This slice adds new packages, new tables and new routes. It changes no
> existing canonical schema, no existing migration, no existing route contract, no D1/D2
> semantics and no E1 status semantics. Where it needs a relationship Layer 1 does not carry, it
> derives it in its own tables and records how.

---

## Part A — Specification

### A1. Business objective

Surface, with verifiable evidence, the customers whose **service relationship is actively
deteriorating** while **commercial exposure is live**, and produce an executive brief a human
can approve or reject.

### A2. Executive question

"Which customers currently require executive attention, why, and what should we do?"

Demonstration instance: *"Why is Meridian Textiles at risk, and what should the CEO do?"*

### A3. Personas

| Persona | Need |
|---|---|
| CEO / executive sponsor | A short, cited brief; a decision to make |
| Account owner (EMP-007, Vikram Pillai) | To know their account reached executive attention and why |
| Head of Customer Support (EMP-004, Karan Kapoor) | To see which breaches drove the escalation |

### A4. Definitions — fixed before any code

| Term | Definition |
|---|---|
| **Risk** | Observable deterioration in the service relationship. **Not** churn probability. Expressed as an ordinal band, never a percentage |
| **Risk band** | `NONE` / `WATCH` / `ELEVATED` / `CRITICAL`, assigned by a versioned decision table in configuration |
| **Policy escalation state** | Boolean. True when the customer satisfies DOC-003's stated rule: three or more tickets created within **any** 14-day window, where that window ends within `lookback_days` of `as_of` |
| **SLA resolution-target breach** | A ticket whose elapsed business days exceed DOC-003's target for its priority (high: 1; medium: 5). For resolved tickets, created→resolved. For open tickets, created→`as_of` |
| **Active deterioration** | Ticket velocity inside the lookback window plus open high-priority tickets. Drives the band |
| **Chronic backlog** | An open ticket far past target but isolated in time. Reported separately. **Never** drives the band |
| **Commercial exposure** | Active deals with stage, probability, amount and currency, reported **per currency**. Never summed across currencies. Never an input to the risk band |
| **Executive-worthy** | Risk band ≥ `ELEVATED` **and** at least one live commercial linkage (an active deal, an active project, or a linked contract document) |
| **`as_of`** | The date every computation is evaluated at. Resolution: explicit argument → `VS01_AS_OF` → `max(support_tickets.created_at)` in the scoped source system. **`now()` is forbidden** |
| **Scope** | One `source_system`, the declared system of record. Default `csv_demo` |

### A5. End-to-end workflow

```
  operator / API caller
        │  as_of, source_system, [customer]
        ▼
  1. Scope resolution        source_system + as_of resolved and recorded
        ▼
  2. Relationship model      customer neighbourhood, each edge carrying its basis
        ▼
  3. Signal engine           deterministic signals per customer (A10)
        ▼
  4. Risk band               decision table → band + list of satisfied rules
        ▼
  5. Evidence links          derived customer↔document links + policy citations
        ▼
  6. SupportRiskAnalyst      sees tickets + SLA rules only  → SupportFinding
     CommercialContextAnalyst sees deals/projects/contracts only → CommercialFinding
        ▼
  7. ExecutiveReconciler     executive-worthiness, ordering, action from catalogue
        ▼
  8. Brief                   templated, every fact cited, content-hashed → DRAFT
        ▼
  9. Human decision          APPROVED / REJECTED bound to the content hash
        ▼
  (no executor exists)
```

### A6. Trigger

Explicit only: `POST /api/v1/risk/assessments` or `make verify-vs01` / `scripts/vs01_brief.py`.
No scheduler, no event listener, no background worker.

### A7. Inputs

`as_of: date | None`, `source_system: str = "csv_demo"`, `customer_source_id: str | None`,
`lookback_days: int` (from config, default 90), `rules_version: str` (from config).

### A8. Required Layer 1 contracts (consumed, unchanged)

| Contract | Use |
|---|---|
| `customers` | Identity, segment, industry, status, `owner_source_id` |
| `support_tickets` | `customer_id` FK, priority, status, category, `created_at`, `resolved_at`, `assignee_source_id` |
| `deals` | `customer_id` FK, stage, amount, currency, probability, `expected_close_date`, `is_active` |
| `projects` | `customer_id` FK, status, `is_active` |
| `employees` | Name, department, title, `manager_source_id` |
| `documents` | `title`, `document_type`, `body_text`, `source_uri` |
| `GET /api/v1/entities/{type}` | Available but **not** used internally; VS-01 reads through repositories in-process |

VS-01 requires **no Layer 1 contract extension.** This is a deliberate design constraint.

### A9. Relationship model (the "graph")

Nodes: `Customer`, `SupportTicket`, `Deal`, `Project`, `Employee`, `Document`.

| Edge | Basis | Source |
|---|---|---|
| `customer_has_ticket` | `CANONICAL_FK` | `support_tickets.customer_id` |
| `customer_has_deal` | `CANONICAL_FK` | `deals.customer_id` |
| `customer_has_project` | `CANONICAL_FK` | `projects.customer_id` |
| `customer_owned_by` | `SOURCE_KEY_JOIN` | `customers.owner_source_id` → employee |
| `ticket_assigned_to` | `SOURCE_KEY_JOIN` | `support_tickets.assignee_source_id` |
| `deal_owned_by` | `SOURCE_KEY_JOIN` | `deals.owner_source_id` |
| `employee_reports_to` | `SOURCE_KEY_JOIN` | `employees.manager_source_id` |
| `document_owned_by` | `SOURCE_KEY_JOIN` | `documents.owner_source_id` |
| `document_mentions_customer` | `DERIVED_TEXT_MATCH` | Id token or exact full-name match (A11) |
| `document_relates_to_topic` | `DERIVED_TOPIC_MATCH` | Category overlap. Supporting only |

Queries the model must answer:

1. `neighbourhood(customer, depth=1)` — tickets, deals, projects, account owner.
2. `escalation_path(customer)` — account owner → manager (EMP-007 → EMP-002), plus the support
   owner of each open ticket and their manager (→ EMP-004).
3. `documents_for(customer)` — derived links with basis and confidence.
4. `policy_documents()` — `document_type = 'policy'`.

Every returned edge carries `basis`; `DERIVED_*` edges additionally carry the matched token and
its character offset.

### A10. Signals (deterministic, all computed `as_of`)

| # | Signal | Definition | Band input? |
|---|---|---|---|
| S1 | `open_ticket_count` | tickets with `status='open'` | yes |
| S2 | `open_high_priority_count` | `status='open' and priority='high'` | yes |
| S3 | `tickets_in_lookback` | `created_at` within `lookback_days` of `as_of` | yes |
| S4 | `max_tickets_in_14d_window` | max count in any 14-day window whose end is within lookback | yes |
| S5 | `policy_escalation_state` | `S4 >= 3` (threshold from DOC-003, in config) | yes |
| S6 | `days_since_last_ticket` | `as_of - max(created_at)` | yes |
| S7 | `sla_breach_count` | breaching tickets (A4), business days | context |
| S8 | `open_sla_breach_high_count` | open, high, past target | yes |
| S9 | `stale_open_ticket_count` | open and > `stale_days` (config) past target | **no** — chronic backlog (§4.4 of strategy) |
| S10 | `dominant_ticket_category` | modal category and its share | context |
| S11 | `active_deal_count` / stages / probabilities | from `deals` where `is_active` | worthiness only |
| S12 | `exposure_by_currency` | `{currency: [(deal, amount, probability)]}` | **no** |
| S13 | `active_project_count` | from `projects` where `is_active` | worthiness only |
| S14 | `contract_document_present` | a linked `document_type='contract'` | worthiness only |

Verified expected values for CUST-007 at `as_of = 2026-09-18`: S1=4, S2=4, S3=5, S4=5
(2026-08-18 → 2026-08-31), S5=true, S6=22, S7=5, S8=3, S10=performance (3/5), S11=1
(negotiation, 90%), S12={USD: [(DEAL-001, 5361.44, 90)]}, S13=0, S14=true (DOC-006).

### A11. Derived document links

Two accepted bases, with different standing:

| Basis | Rule | May derive signals? |
|---|---|---|
| `ID_TOKEN` | The canonical `source_id` appears as a whole token in title or body | Yes |
| `EXACT_NAME` | The customer's **full** name matches exactly, case-insensitively, at a token boundary | Yes |
| `TOPIC` | Document type/title overlaps the customer's dominant ticket category | **No** — supporting evidence only |

Substring name matching is **forbidden** and pinned by a test: the dataset contains
"Meridian Textiles", "Westbrook Textiles" and "Northstar Textiles".

Measured expected result for CUST-007: `ID_TOKEN` → DOC-005, DOC-006, DOC-009;
`EXACT_NAME` → DOC-006, DOC-009 (also matched by id token); `TOPIC` → DOC-010, supporting only.

### A12. Retrieval and RAG

No embeddings, no vector store, no language model. Evidence selection is deterministic:
customer-linked documents by A11; policy documents cited **structurally**, because the rule
configuration names its source document (DOC-003 for the escalation rule and the SLA targets).

### A13. ML

None. No model is trained, served or referenced.

### A14. Analyst modules, scopes and tools

| Module | Permitted reads | Forbidden reads | Output |
|---|---|---|---|
| `SupportRiskAnalyst` | `support_tickets`, SLA rule config, policy documents | `deals`, `projects`, monetary fields | `SupportFinding`: band, satisfied rules, S1–S10, breach list, escalation state, citations |
| `CommercialContextAnalyst` | `deals`, `projects`, contract documents | `support_tickets` | `CommercialFinding`: per-currency exposure, stages, probabilities, contract terms, citations |
| `ExecutiveReconciler` | The two findings, plus customer identity and the account owner | Raw tables | `ExecutiveBrief`: worthiness, priority, action, narrative, all citations |

Each module declares its scope as data; a repository facade enforces it at runtime and a test
asserts the enforcement (`SupportRiskAnalyst` attempting to read `deals` must raise).

### A15. Reconciliation logic

Deterministic and ordered:

1. Executive-worthy iff band ≥ `ELEVATED` **and** (`S11 > 0` or `S13 > 0` or `S14`).
2. Priority ordering: band descending → `S8` descending → `S4` descending → `source_id`
   ascending. **Monetary values are not a sort key.**
3. Action selected from the catalogue by first matching precondition set, in declared order.
4. Narrative rendered from a template; every clause is bound to a citation.

There is no model in this loop. Nothing is inferred.

### A16. Action catalogue (versioned config)

| Action | Preconditions |
|---|---|
| `ESCALATE_TO_ACCOUNT_OWNER_PER_SLA` | `S5` true |
| `SCHEDULE_EXECUTIVE_SPONSOR_CALL` | `S5` true and `S11 > 0` |
| `ASSIGN_DEDICATED_SUPPORT_OWNER` | `S8 >= 2` |
| `PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED` | `S8 >= 1` and an active deal in `negotiation` |
| `REVIEW_INVOICE_DISPUTE` | an open ticket with category `billing` |
| `NO_ACTION` | band `NONE` |

CUST-007 at the pinned `as_of` matches the first five.

### A17. Brief structure and evidence contract

Sections: identity · risk state and the rules that produced it · evidence (signals, each with
the ticket ids behind it) · commercial context (per currency) · policy and contract context ·
chronic-backlog observations · recommended actions · escalation path · limitations.

**Evidence contract:** every asserted fact carries `{kind: "record", entity, id, field}` or
`{kind: "document", document_id, start, end}`. A brief containing an unresolvable citation is
invalid and the generator raises.

**Absence is stated, never omitted.** CUST-007 has no project; the brief must say so rather than
render `0` or drop the section.

### A18. Persistence (new tables only, `public` schema, new Alembic revision from `8bfd73b6af60`)

| Table | Key columns |
|---|---|
| `document_customer_links` | `id`, `document_id` FK, `customer_id` FK, `basis`, `matched_token`, `match_start`, `match_end`, `confidence`, `linker_version`, `computed_at` |
| `risk_assessments` | `id`, `customer_id` FK, `as_of`, `source_system`, `rules_version`, `band`, `satisfied_rules` (JSONB), `signals` (JSONB), `executive_worthy`, `computed_at`, unique on `(customer_id, as_of, rules_version, linker_version)` |
| `risk_briefs` | `id`, `assessment_id` FK, `status` (`DRAFT`), `content` (JSONB), `content_hash`, `template_version`, `generated_at`, unique on `(assessment_id, content_hash)` |
| `brief_decisions` | `id`, `brief_id` FK, `content_hash`, `actor`, `decision` (`APPROVED`/`REJECTED`), `note`, `decided_at`, `supersedes_id` nullable. **Append-only** |

Canonical Layer 1 tables are not altered. The migration is additive; its downgrade drops only
the four new tables.

### A19. API (new routes, additive)

| Route | Method | Purpose |
|---|---|---|
| `/api/v1/risk/assessments` | POST | Compute assessments for a scope; body carries `as_of`, `source_system`, optional `customer_source_id` |
| `/api/v1/risk/assessments` | GET | List assessments, filter by `as_of`, band, worthiness; limit/offset |
| `/api/v1/risk/assessments/{id}` | GET | One assessment with signals and satisfied rules |
| `/api/v1/risk/briefs/{id}` | GET | The brief with citations |
| `/api/v1/risk/briefs/{id}/decision` | POST | Record a decision; body carries `actor`, `decision`, `note`, `content_hash` |
| `/api/v1/risk/briefs/{id}/decisions` | GET | Decision history |

Conventions reused from F1/F2 unchanged: envelope, error codes, correlation id, limit/offset,
`Decimal` as JSON string. `content_hash` mismatch on a decision returns a 409-class error.

### A20. UI

None. OpenAPI `/docs` only, consistent with Layer 1. A frontend is a separate, undecided
decision (strategy §12).

### A21. Observability

Reuses `app/core/logging.py` `log_event` and `app/observability/metrics.py` counters. Events:
`vs01.scope_resolved` (as_of, source, resolution path), `vs01.signals_computed` (customer count,
duration), `vs01.band_assigned` (band, rule ids), `vs01.links_derived` (counts by basis),
`vs01.brief_generated` (content hash, citation count), `vs01.decision_recorded` (decision,
actor). No document text, no customer email, no monetary value in any log line.

### A22. Security

| Concern | Control |
|---|---|
| Prompt injection | **Structurally impossible** — no model, no prompt. This is a named reason for the templated design |
| Document text as instruction | Document text appears only as quoted evidence with id and span, length-capped, escaped for the output format. The linker never treats body text as configuration |
| Customer-scope leakage | A brief for customer X must contain no other customer's identifiers — enforced by test |
| Tool/data scope | Repository facade per analyst; enforcement tested (A14) |
| No executor | Static boundary test: no module under the VS-01 packages may import an outbound HTTP/SMTP client. Mirrors G2's boundary tests |
| Approver identity | Recorded but **asserted, not verified** — there is no authentication. Documented as a limitation and a prerequisite for any future executor |
| SQL | ORM/parameterised only, per existing convention |
| Secrets | `make secret-scan` must stay at 0 findings |

### A23. Failure modes

| Failure | Behaviour |
|---|---|
| No tickets for a customer | Band `NONE`, not an error. The 15 ticketless customers and the 4 inactive ones must all succeed |
| `customer_id` FK NULL (unresolved reference) | Ticket/deal excluded from that customer's signals and reported in a `data_quality` note on the brief. Never silently dropped |
| Empty database | Empty result set, not an exception |
| `as_of` earlier than all data | All bands `NONE`; the report states the scope was empty |
| `as_of` in the future | Permitted and recorded; recency signals decay naturally |
| Rules config invalid | Refuse at load with a message naming the broken rule; no partial assessment |
| Document with NULL `body_text` | Skipped by the linker without error |
| Decision on a stale `content_hash` | Rejected with a conflict error; the stale brief is never approved |
| Two concurrent assessments, same scope | Unique constraint makes the second a no-op read of the first |

### A24. Idempotency and determinism

- An assessment is a pure function of (`as_of`, `source_system`, `rules_version`,
  `linker_version`, Layer 1 snapshot). Re-running inserts nothing new.
- `content_hash` is computed over the brief's canonical JSON using the **same serialisation
  discipline as `record_hash`** (sorted keys, compact separators, normalised `Decimal`, UTC
  ISO-8601) so it is stable across processes and platforms.
- No `now()`, no random, no dict-ordering dependence, no locale dependence. Business-day
  arithmetic uses a fixed weekday rule with no holiday calendar — stated as a limitation.

### A25. Evaluation strategy

| Layer | What it proves |
|---|---|
| Unit | Every signal against hand-computed expected values; band decision table; catalogue preconditions; link bases; business-day arithmetic; `content_hash` stability |
| Contract | Analyst scope enforcement; evidence-contract validity; API shapes from OpenAPI |
| Integration | Migration up/down; unique constraints; append-only decisions; content-hash conflict; idempotent re-run |
| End-to-end | Full scenario over HTTP: assess → brief → approve; then reject path |
| Acceptance | `scripts/vs01_acceptance.py` / `make verify-vs01`, in the style of `verify_layer1.py`: named checks, each with a pass condition and a line of observed evidence |

**Named high-value tests**

1. **Single-escalation test.** At the pinned `as_of`, CUST-007 is the **only** customer with
   `policy_escalation_state = true` and the only `CRITICAL` one. (Measured: true across all 50.)
2. **DOC-005 leave-out test.** Remove DOC-005 from the corpus; band, every signal and the
   escalation state must be byte-identical. Proves computation, not paraphrase.
3. **Amount-invariance test.** Multiply every deal amount by 1000; the risk ranking must not
   change. Guards against a blended score.
4. **Chronic-backlog test.** CUST-048 (TKT-005 open since January) and CUST-009 (TKT-010) must
   **not** outrank CUST-007, and their stale tickets must appear as backlog observations rather
   than escalation drivers.
5. **Substring-safety test.** "Westbrook Textiles" and "Northstar Textiles" must acquire no link
   to Meridian documents.
6. **Citation-resolution test.** Every citation in every brief for all 50 customers resolves.
7. **Scope-leakage test.** No brief contains another customer's `source_id`, name or email.
8. **Negative-case test.** The 4 inactive customers and the 15 ticketless customers all yield
   `NONE` and `executive_worthy = false`.
9. **Rule-liveness mutation.** Changing the escalation threshold from 3 to 6 must make CUST-007
   non-escalated. Proves the config is load-bearing.
10. **Determinism test.** Two runs in separate processes produce identical `content_hash`.

Mutation testing follows the project's existing ad-hoc textual harness, targeting the signal
engine, the decision table and the linker.

### A26. Fixtures and synthetic data

No new demo data and **no change to `data/demo/`**. New fixtures only:

- a corpus fixture with DOC-005 removed (test 2);
- a deal fixture with amounts scaled (test 3);
- a documents fixture containing a customer name as a substring of another (test 5);
- a tickets fixture with an unresolved `customer_source_id` (A23);
- an adversarial document fixture containing instruction-like text, asserting it is rendered as
  quoted evidence and never interpreted.

### A27. Acceptance criteria (binary)

1. `make verify-vs01` exits 0 against a running stack with the demo dataset ingested.
2. At the pinned `as_of`, exactly one customer is `CRITICAL` and executive-worthy: CUST-007.
3. Its brief cites, each with a resolvable citation: 5 tickets in a 9-day span; 4 open; 4 high;
   3 open high-priority SLA breaches; dominant category `performance`; DEAL-001 in `negotiation`
   at 90% for USD 5,361.44 (currency named, never summed with INR); DOC-003's escalation rule;
   DOC-006's 36-month term and 90-day notice; DOC-009's account-review actions.
4. The brief states that CUST-007 has no active project.
5. Recommended actions are exactly the five catalogue entries whose preconditions match.
6. Every citation across all 50 briefs resolves.
7. Tests 1–10 of A25 pass.
8. Two runs produce identical `content_hash`; a re-run inserts no rows.
9. Approving a brief writes one decision row; a second decision on the same hash is refused
   unless it declares `supersedes_id`; rejection is recorded and no action is executable.
10. Regression: the full Layer 1 suite passes unchanged; `app/` coverage stays at 100%; ruff and
    mypy stay at baseline (69 findings / 9 errors); secret scan stays at 0.

### A28. Demo scenario (reviewer-facing, ~4 minutes)

1. `make docker-up && make migrate && make ingest-demo` — Layer 1, unchanged.
2. `POST /api/v1/risk/assessments {"as_of": "2026-09-18"}` — 50 customers assessed.
3. `GET /api/v1/risk/assessments?executive_worthy=true` — one row: Meridian Textiles.
4. `GET /api/v1/risk/briefs/{id}` — the brief, with every fact citing a record or a document
   span.
5. Open DOC-003 and DOC-006 at the cited spans; the reviewer verifies two citations by hand.
6. `POST .../decision {"decision": "REJECTED", ...}` then `GET .../decisions` — governance is a
   record, and nothing executed.
7. Re-run step 2 — identical hash, no new rows.
8. `pytest -k doc005_leave_out` — the conclusion survives removal of the document that states
   it in prose.

No network, no API key, no model, no external service.

### A29. Known limitations (must appear in the brief and the README section)

Single source system; no cross-source entity resolution; document links are derived, not
provenance-backed; `DERIVED_TOPIC_MATCH` is supporting evidence only; no FX, so no cross-currency
total; business-day arithmetic has no holiday calendar; the risk band is a policy artefact, not a
probability; approver identity is asserted, not authenticated; the dataset is synthetic, 233 rows;
`employees.organization_id` remains NULL (Layer 1 gap).

### A30. Future extensions

Risk trend over successive `as_of` dates (VS-06 makes it longitudinal); FX-normalised exposure
(VS-02); model-generated narrative over the same deterministic facts (VS-04); open-vocabulary
evidence retrieval (VS-05); calibrated churn probability (VS-07, conditional).

### A31. Dependencies

None beyond accepted Layer 1. VS-01 is the root of the slice graph and introduces the shared
components listed in strategy §11.

### A32. Explicitly out of scope

Churn probability; forecasting; Neo4j; embeddings or a vector store; any language model;
multi-source aggregation; cross-currency totals; scheduling or notification; authentication;
any executor; a frontend; changes to `data/demo/`; changes to any Layer 1 module's behaviour.

---

## Part B — Milestones

Each milestone is one commit, verified before the next begins, following the project's existing
one-task-at-a-time workflow. **Frozen throughout:** D1/D2 semantics, E1 persistence and status
semantics, F1/F2 route contracts, G1 logging and metric semantics, G2 security behaviour, H
test layers, I acceptance, and `data/demo/`.

### M0 — Pre-flight (no production code)

- **Objective.** Baselines recorded before anything changes.
- **Change.** Record full-suite count, coverage, ruff findings, mypy errors, secret-scan
  findings, and `make verify-layer1` output. Revert the stray working-tree edit in `README.md`
  (two box-drawing characters replaced by hyphens in the architecture diagram) so the tree is
  clean.
- **After.** A known-good baseline every later milestone is measured against.
- **Non-goals.** Any new module.

### M1 — Domain contract, scope and `as_of`

- **Objective.** The vocabulary of A4 exists in code; `now()` is impossible.
- **Files.** `app/intelligence/contract.py` (enums, dataclasses: `RiskBand`, `EdgeBasis`,
  `LinkBasis`, `SignalSet`, `Citation`, `SupportFinding`, `CommercialFinding`, `ExecutiveBrief`),
  `app/intelligence/scope.py` (`resolve_scope()`), `config/intelligence/risk_rules.yaml`.
- **Contracts.** `resolve_scope(as_of=None, source_system="csv_demo") -> Scope`, recording which
  resolution path produced `as_of`.
- **Tests.** Resolution order; empty-database fallback; a static boundary test asserting no
  module under `app/intelligence/` references `datetime.now`, `date.today` or `utcnow`.
- **Acceptance.** Scope resolves from the demo database to 2026-08-27; the boundary test fails
  if `now()` is introduced.
- **Rollback.** Delete the package; nothing else depends on it yet.
- **Non-goals.** Signals, persistence, API.

### M2 — Relationship model

- **Objective.** A9's nodes, edges and four queries, every edge carrying its basis.
- **Files.** `app/relationships/model.py`, `app/relationships/queries.py`,
  `app/relationships/edges.py`. Read-only; the caller owns the session, per the existing
  repository convention.
- **Tests.** Each edge type resolves on the demo dataset; `SOURCE_KEY_JOIN` never crosses
  `source_system`; a NULL FK yields no edge rather than an error; `escalation_path(CUST-007)`
  returns EMP-007 → EMP-002 plus the support assignees and EMP-004.
- **Acceptance.** The four queries return the measured expected neighbourhoods; every edge
  reports a basis.
- **Non-goals.** Derived document links (M4), any graph database.

### M3 — Signal engine and risk band

- **Objective.** S1–S14 and the decision table.
- **Files.** `app/intelligence/signals.py`, `app/intelligence/bands.py`,
  `app/intelligence/business_days.py`, `config/intelligence/risk_rules.yaml`.
- **Tests.** Each signal against hand-computed values for CUST-007, CUST-009, CUST-048, a
  ticketless customer and an inactive customer; the 14-day sliding window at boundaries (13/14/15
  days); business-day arithmetic across weekends; band assignment for every row of the decision
  table; rule-liveness mutation (threshold 3 → 6); amount invariance.
- **Acceptance.** CUST-007 is the only escalated and only `CRITICAL` customer at the pinned
  `as_of`; CUST-048 and CUST-009 rank below it with their stale tickets reported as backlog.
- **Non-goals.** Documents, persistence, briefs.

### M4 — Evidence links and citation contract

- **Objective.** A11 link derivation and the A17 evidence contract.
- **Files.** `app/evidence/linker.py`, `app/evidence/citations.py`,
  `app/persistence/models/document_customer_link.py`, repository, and the additive Alembic
  revision for `document_customer_links` branching from `8bfd73b6af60`.
- **Tests.** Id-token matching finds DOC-005/006/009 for CUST-007; exact-name matching finds
  DOC-006/009; substring safety for the three "… Textiles" customers; NULL `body_text` skipped;
  spans resolve to the quoted text; citation resolution for records and documents; adversarial
  document text is quoted, never interpreted.
- **Acceptance.** Links reproduce the measured expectation; every citation resolves; the
  migration's downgrade drops only the new table.
- **Non-goals.** Embeddings, topic links driving signals.

### M5 — Analyst modules with enforced scopes

- **Objective.** A14's two analysts and the scope facade.
- **Files.** `app/analysts/base.py` (scope declaration + facade), `app/analysts/support_risk.py`,
  `app/analysts/commercial_context.py`.
- **Tests.** `SupportRiskAnalyst` reading `deals` raises; `CommercialContextAnalyst` reading
  `support_tickets` raises; each finding validates against its schema; findings carry citations;
  exposure is per currency and never summed.
- **Acceptance.** Both analysts produce the measured findings for CUST-007; scope violations are
  test-enforced, not documented conventions.
- **Non-goals.** Reconciliation, LLM.

### M6 — Reconciler, action catalogue and brief

- **Objective.** A15–A17: worthiness, ordering, action selection, templated brief, content hash.
- **Files.** `app/decisions/reconciler.py`, `app/decisions/actions.py`,
  `app/decisions/brief.py`, `app/decisions/templates/`,
  `config/intelligence/action_catalogue.yaml`, models and migration for `risk_assessments` and
  `risk_briefs`.
- **Tests.** Worthiness truth table; ordering with money perturbed; catalogue preconditions;
  absence rendered as a stated absence (CUST-007 has no project); citation resolution across all
  50 briefs; `content_hash` stable across processes; idempotent re-run inserts nothing; the
  DOC-005 leave-out test.
- **Acceptance.** The CUST-007 brief matches a committed golden file byte-for-byte at the pinned
  `as_of`, and contains every item of A27.3.
- **Non-goals.** Approval, API, narrative generated by a model.

### M7 — Human approval boundary

- **Objective.** A18's `brief_decisions` and the no-executor invariant.
- **Files.** `app/decisions/approval.py`, model, repository, migration.
- **Tests.** Append-only (an update attempt fails); stale `content_hash` refused; a second
  decision requires `supersedes_id`; rejection recorded; **static boundary test** asserting no
  module under `app/intelligence/`, `app/analysts/`, `app/decisions/` or `app/relationships/`
  imports `smtplib`, an outbound HTTP client or any source-writing path.
- **Acceptance.** A rejected brief is recorded and provably cannot execute; the boundary test
  fails if an outbound client is introduced.
- **Non-goals.** Authentication (stated as a prerequisite for any future executor), execution.

### M8 — API routes

- **Objective.** A19, additive and consistent with F1/F2.
- **Files.** `app/api/v1/risk.py`, `app/api/v1/schemas.py` additions, router registration.
- **Tests.** OpenAPI-discovered contract tests in the H4 style; read-only verbs except the two
  documented POSTs; pagination; error codes; hash-conflict response; no document text or email in
  error bodies.
- **Acceptance.** Existing F1/F2 contract tests still pass unchanged; new routes appear in
  OpenAPI with typed models.
- **Non-goals.** UI, authentication.

### M9 — End-to-end acceptance, hardening and evaluation

- **Objective.** The A28 demo as an executable command, and the A25 test layers complete.
- **Files.** `scripts/vs01_acceptance.py`, `make verify-vs01`, `tests/e2e/test_vs01_scenario.py`,
  the fixtures of A26, README section, and a phase record appended to
  `CONTEXT/AI_CEO_PROJECT_CONTEXT.md`.
- **Tests.** The full A28 flow over HTTP; every A25 named test; mutation audit over the signal
  engine, decision table and linker.
- **Acceptance.** All ten criteria of A27, including the Layer 1 regression and baseline checks.
- **Non-goals.** Starting VS-02.

### Milestone dependency order

`M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9`

M2 and M3 could proceed in parallel if needed; every other edge is a hard dependency.
