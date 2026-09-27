# AI CEO — Project Context Document
**Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
**Last updated: 2026-09-21 | Maintained by: Yuvraj Gaykhe**

> **Purpose**: This file is the single source of truth for all confirmed project understanding, design decisions, and task state. Read this file at the start of any new session before asking questions or writing code.

---

## 1. What the Project Is

**AI CEO** is a multi-layer enterprise intelligence platform. It connects a company's fragmented systems of record — CRM, ERP, HRMS, support desk — normalizes their data into a shared canonical model, builds a knowledge graph over those entities, runs a team of specialized AI agents to reason across them, and surfaces coordinated executive recommendations for human review. A human executive approves any recommendation before it triggers an external action.

The platform is designed for small to mid-sized companies that cannot afford a Salesforce/SAP-scale deployment but still suffer from data fragmentation. The prototype uses demo/simulated enterprise data.

---

## 2. The Problem Being Solved

Four recurring cross-functional gaps:

1. **Fragmented customer risk signals** — churn indicators in one system never reach the teams that need them.
2. **Manual cross-functional reporting** — executives assemble numbers that already exist across five systems.
3. **Reactive budget allocation** — marketing/resource budgets set periodically instead of adjusted against real-time performance.
4. **No shared institutional memory** — contracts, policies, and past decisions live in scattered documents that cannot be queried in natural language.

---

## 3. The Five-Stage Architecture (Overall System)

```
CRM / ERP / HRMS Systems
        ↓
  Connector Layer          ← THIS IS LAYER 1 (current scope)
        ↓
Enterprise Twin + Knowledge Graph   ← Layer 2 (future)
        ↓
Multi-Agent AI (14 specialized agents + CEO Agent)   ← Layer 3/4 (future)
        ↓
Human Sign-off + Action   ← Layer 5 (future)
```

**IMPORTANT**: Layer 1 is complete and **frozen**. Everything after Layer 1 is built as
end-to-end **vertical slices** rather than as horizontal layer phases — see
`CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md` for the rationale, the data-feasibility verdict and
the full slice roadmap, and `CONTEXT/VS01_IMPLEMENTATION_PLAN.md` for the first slice. The
five-stage diagram above remains the destination; slices are how it is reached. Nothing in
those two documents is implemented.

---

## 4. Layer 1 — The Connector Layer

### 4.1 Primary Objective

Build a production-style prototype ingestion subsystem that:
- Reads multiple enterprise data sources through a common adapter interface
- Validates and normalizes records into a source-neutral canonical schema
- Persists canonical entities in PostgreSQL with full provenance tracking
- Tracks ingestion runs with truthful counts and structured error records
- Exposes all normalized data through a versioned FastAPI at `/api/v1`

### 4.2 Layer 1 Data Flow

```
Source Systems (CSV / Odoo mock / REST mock)
        ↓ [Connector Interface]
Raw Ingestion Boundary (source payload + provenance + run_id)
        ↓ [Normalization Engine]
Normalization (field mapping, type coercion, enum/date/currency/boolean normalization, record_hash)
        ↓ [Validation + Quality Gate]
Quality Gate (completeness, validity, uniqueness, FK resolution, severity: ERROR / WARNING / INFO)
        ↓ [Persistence]
Canonical PostgreSQL Store (7 entity tables + 5 operational tables)
        ↓ [FastAPI]
Stable API Contract → Layer 2 Consumers (future)
```

### 4.3 What Layer 1 IS Responsible For

- Connecting to enterprise-style sources (CSV, local Odoo-compatible mock, generic REST mock)
- Extracting records, persisting raw source payloads with full provenance
- Normalizing and validating records into the canonical schema (no LLMs — fully deterministic)
- Idempotent upsert into PostgreSQL keyed by `(source_system, source_entity, source_id)`
- Tracking every ingestion run (status: SUCCESS / PARTIAL_SUCCESS / FAILED / NOOP)
- Quarantining invalid records with structured error records
- Exposing canonical entities + run metadata through a versioned REST API
- Read-only safety: Layer 1 never writes back to any source system

### 4.4 What Layer 1 is NOT Responsible For

| Out of scope | How it is handled now |
|---|---|
| Neo4j knowledge graph | Define canonical entities as downstream-ready contracts only |
| Vector embeddings / RAG | Do not implement; preserve body_text and provenance for later |
| Churn prediction model | Do not train or serve in Layer 1 |
| Revenue/demand forecasting | Do not train or serve in Layer 1 |
| 14 functional agents + CEO Agent | Do not implement |
| LLM reasoning | Do not use LLMs for deterministic normalization |
| Source write-back | Forbidden — read-only only |
| Frontend dashboard | Optional minimal OpenAPI /docs only; no full UI |
| Production enterprise credentials | Use adapters, mocks, and demo-safe connectors |

---

## 5. Confirmed Design Decisions

All items below were explicitly confirmed during the interview. Do not reverse without re-interviewing.

| Decision | Confirmed value |
|---|---|
| Folder structure | Guideline, not prescription. Preserve architectural separation: connector → raw → normalize → validate → persist → API |
| ORM | Synchronous SQLAlchemy |
| Migrations | Alembic (versioned, not startup-script-based) |
| FastAPI route style | Synchronous routes, sync SQLAlchemy sessions, TestClient for tests |
| Database | PostgreSQL only (no Redis, no additional stores in Layer 1) |
| Test tooling | pytest only (no testcontainers, no httpx async client) |
| Odoo connector | Deterministic local mock — no live Odoo connection |
| Docker Compose services | postgres + api + mock-source (one container for both connector paths) |
| Mock-source API shape | Plain REST JSON; Odoo connector targets /odoo/..., REST connector targets /rest/... on the same container |
| Mock-source framework | PROPOSED DECISION — to be confirmed at Task C3 |
| Demo data source | Static CSVs committed to repo (fixed random seed); mock-source reads same CSVs and serves as JSON |
| Organization entity | One row — the single internal demo company (e.g. "Acme Corp") |
| Document body_text | Full extracted text stored in Postgres |
| API pagination | Limit/offset on all canonical entity endpoints |
| Unresolved FK behavior | Canonical FK = NULL + source_id preserved + WARNING in ingestion_errors |
| Checkpoint/cursor storage | Separate ingestion_cursors table: (source_system, source_entity) → last_cursor + last_successful_run_id |
| record_hash scope | All canonical business fields per entity, excluding provenance fields (ingested_at, ingestion_run_id) |
| is_active entities | Employees, customers, deals, projects only (not organizations, support_tickets, or documents) |
| Dependency management | Standard pip + pyproject.toml + virtualenv |
| Code location | Directly in /Users/yuvrajgaykhe/SEM7/FINAL YEAR PROJECT/ |
| Language | Clean English throughout (no i18n framework) |
| Timeline | Correctness first, no hard deadline |
| Layer sequencing | Full Layer 1 acceptance before any Layer 2 work begins |
| Build approval | Task-level approval required before each individual task |
| Post-Layer-1 sequencing | End-to-end vertical slices, not horizontal layer phases (confirmed 2026-09-18) |
| Graph substrate | PostgreSQL relationship service behind a substrate-agnostic interface; Neo4j only when a slice needs path queries (confirmed 2026-09-18) |
| Document → customer linkage | Derived in Layer 2 with a recorded basis; Layer 1 contract untouched (confirmed 2026-09-18) |
| ML data strategy | Layer 1 frozen; a separate versioned Layer 2 `analytics` projection carries longitudinal/synthetic data with per-row lineage (confirmed 2026-09-18) |
| Language-model runtime | Templated generation first; every call behind a `LanguageModel` interface with a deterministic fake default and a committed response cache; provider deferred (confirmed 2026-09-18) |
| `as_of` evaluation | Every intelligence module takes an explicit `as_of`; `now()` is forbidden (confirmed 2026-09-18) |
| Risk representation | Ordinal band from a versioned decision table; money is never an input to the band (confirmed 2026-09-18) |
| Conflict reconciliation | Owned by **VS-01**, not deferred to VS-04: the data already contains a genuine Sales/Support conflict over DEAL-001 (confirmed 2026-09-18, v2) |
| Recorded dissent | A losing functional position is preserved in the brief with its citations, never averaged away or deleted (confirmed 2026-09-18, v2) |
| Analyst isolation | Analysts receive pre-built typed context objects and **never a database session**, so scope is enforced by construction (confirmed 2026-09-18, v2) |
| Assessment identity | Includes a `layer1_fingerprint` over the scoped canonical `record_hash` values and counts, so a re-run after new ingestion cannot return stale intelligence (confirmed 2026-09-18, v2) |
| Approval binding | Binds to the decision **payload** hash, excluding timestamps and template version, so a template edit cannot invalidate prior approvals (confirmed 2026-09-18, v2) |
| Executive-worthiness | Gated only on canonical-FK commercial linkage; derived document links are evidence, never a gate (confirmed 2026-09-18, v2) |

---

## 6. Canonical Schema (PostgreSQL)

### 6.1 Universal Provenance Fields (on every entity)

| Field | Type | Notes |
|---|---|---|
| id | UUID | Internal canonical primary key |
| source_system | string | e.g. csv_demo, odoo_mock, rest_mock |
| source_entity | string | Original entity/table/resource type |
| source_id | string | Stable source identifier |
| source_updated_at | datetime (nullable) | Timestamp from source when available |
| ingested_at | datetime | When this version entered Layer 1 |
| ingestion_run_id | UUID | Run that produced/updated the record |
| record_hash | string | Hash of all canonical business fields (excludes provenance) |

### 6.2 Canonical Entity Table Summary

| Entity | is_active? |
|---|---|
| organizations | No |
| employees | Yes |
| customers | Yes |
| deals | Yes |
| projects | Yes |
| support_tickets | No |
| documents | No |

### 6.3 Operational Tables (5 total)

| Table | Purpose |
|---|---|
| ingestion_runs | One row per execution; source, status, timing, counts, error summary |
| ingestion_errors | Structured rejected-record and connector errors |
| source_records | Raw/source payload + provenance + content hash |
| connector_configs | Non-secret connector configuration; secrets via env var names |
| ingestion_cursors | (source_system, source_entity) → last_cursor + last_successful_run_id |

---

## 7. Connector Specification

### 7.1 Connector Interface (Protocol)

```python
class SourceConnector(Protocol):
    source_name: str
    source_type: str
    def health_check(self) -> ConnectorHealth: ...
    def list_entities(self) -> list[SourceEntity]: ...
    def fetch_entities(self, entity_type: str, cursor: str | None, page_size: int) -> Page[dict]: ...
    def get_entity(self, entity_type: str, source_id: str) -> dict: ...
    def capabilities(self) -> ConnectorCapabilities: ...
```

### 7.2 Three Connectors

1. **CSV Connector** — reads static CSV files from `data/demo/`; configurable column mapping; row identity via configured business key or stable row hash.
2. **Odoo Mock Connector** — targets `/odoo/...` on the mock-source container; read-only, paginated; Odoo-specific details isolated inside the adapter.
3. **Generic REST Connector** — configurable base URL, auth (bearer/API-key), endpoint, pagination; GET-only; retry with exponential backoff; targets `/rest/...` on mock-source.

**Non-negotiable connector rules:**
- Every connector must be GET/read-only — no POST/PUT/DELETE/PATCH.
- Odoo-specific field names must not leak beyond the adapter boundary.
- Connector health check is separate from application liveness/readiness.

---

## 8. API Contract (FastAPI /api/v1)

| Endpoint | Method | Purpose |
|---|---|---|
| /api/v1/health | GET | Liveness/readiness |
| /api/v1/sources | GET | List configured connectors + capabilities |
| /api/v1/sources/{source}/health | GET | Connector health check |
| /api/v1/ingestion/runs | POST | Start an ingestion run |
| /api/v1/ingestion/runs | GET | List runs with filters |
| /api/v1/ingestion/runs/{run_id} | GET | Run detail + counts |
| /api/v1/ingestion/runs/{run_id}/errors | GET | Structured ingestion errors |
| /api/v1/entities/{entity_type} | GET | Query canonical entities (limit/offset pagination) |
| /api/v1/entities/{entity_type}/{id} | GET | Fetch one canonical entity |
| /api/v1/metrics/ingestion | GET | Operational ingestion metrics |

---

## 9. Demo Data Requirements

| Entity | Minimum count |
|---|---|
| Customers | 50 |
| Employees | 20 |
| Deals | 40 (with stages, amounts, owners, dates) |
| Projects | 20 |
| Support tickets | 75 (including repeated tickets for selected customers) |
| Documents | 10 (with useful text metadata + full body_text) |

- Fixed random seed → static CSV files in `data/demo/`
- One organization row ("Acme Corp" or equivalent)
- Separate bad-fixture file with deliberate quality issues
- Include customer with multiple tickets in short period + active deal (for future churn detection)

---

## 10. Security Non-Negotiables

- All secrets via environment variables — never hardcoded
- Only `.env.example` committed; real `.env` is gitignored
- Connector HTTP methods restricted to GET only
- Parameterized SQL / ORM queries — no string concatenation
- Do not execute Excel formulas/macros
- Human governance boundary: Layer 1 never sends emails, modifies CRM records, or takes external business actions

### 10.1 How these are enforced (Task G2)

- `app/core/security.py`: connector `base_url` validation (http/https, host, port 1–65535, no embedded credentials, query or fragment); REST paths that cannot name another host; timeouts finite and at most 300 s; a GET-only, same-origin, no-redirect HTTP client used by the Odoo mock and REST connectors.
- CSV imports: plain `.csv` file names only; files must resolve inside the data directory (symlinks included), be regular files and stay within `max_file_bytes` (default 50 MiB).
- Secrets: `Settings` hides the database password and URL from repr; engines never echo SQL; `make secret-scan` (`scripts/secret_scan.py`) must report 0 findings over tracked files.
- Tests prove the constraints: static boundaries (no eval/exec/pickle/unsafe YAML, no textual SQL, logging only via `log_event` with exception class names) and an end-to-end canary test showing secrets never reach API responses, OpenAPI, logs or `ingest-demo` output.

---

## 11. Layer 2 Handoff Contract

Layer 1 exposes stable endpoints that Layer 2 consumes without knowing the source system:

```
GET /api/v1/entities/customers
GET /api/v1/entities/deals
GET /api/v1/entities/support_tickets
GET /api/v1/entities/employees
GET /api/v1/entities/projects
GET /api/v1/entities/documents
```

Do not embed Neo4j schema, graph logic, or LLM framework configuration anywhere in Layer 1.

---

## 12. Task Map and Status

**Workflow rule**: One task → implement only that task → verify → report → stop → wait for explicit approval before next task.

| Phase | Task | Description | Status |
|---|---|---|---|
| A — Foundation | A1 | Repository scaffolding | ✅ Complete — pushed (314c19b) |
| A — Foundation | A2 | Docker Compose + service definitions | ✅ Complete — pushed (52124bf) |
| A — Foundation | A3 | Alembic setup + baseline migration (`0001`; the 12 tables arrive in B1's `8bfd73b6af60`) | ✅ Complete — pushed (4d7e524) |
| B — Core Contracts | B1 | SQLAlchemy ORM models | ✅ Complete — pushed (55f423d) |
| B — Core Contracts | B2 | Pydantic canonical schemas | ✅ Complete — pushed (09a42bc, 123a89b) |
| B — Core Contracts | B3 | Pydantic source schemas | ✅ Complete — pushed (e66589c) |
| C — Connectors | C1 | Connector base interface | ✅ Complete — pushed (1e7a8dd) |
| C — Connectors | C2 | CSV connector | ✅ Complete — pushed (b7a836c) |
| C — Connectors | C3 | Mock-source HTTP server | ✅ Complete — pushed (c7110cf) |
| C — Connectors | C4 | Odoo mock connector | ✅ Complete — pushed (62fb748) |
| C — Connectors | C5 | Generic REST connector | ✅ Complete — pushed (b78c4da, 2c4f149) |
| D — Normalization | D1 | Normalization engine | ✅ Complete — pushed (571f9b0, ceaa4d1) |
| D — Normalization | D2 | Validation and quarantine engine | ✅ Complete — pushed (3e53cef) |
| E — Orchestration | E1 | Ingestion orchestrator | ✅ Complete — pushed (0eef137..68ae118) |
| E — Orchestration | E2 | Demo data generation | ✅ Complete — pushed (2b90494..798e431) |
| F — API | F1 | FastAPI routes — health, sources, ingestion | ✅ Complete — pushed (17e906e..1708b49) |
| F — API | F2 | FastAPI routes — canonical entities + metrics | ✅ Complete — pushed (2be74dd, 53693fe) |
| G — Observability | G1 | Structured logging + ingestion metrics counters | ✅ Complete — pushed (4cb6631..1934ea6) |
| G — Observability | G2 | Secret hygiene audit + security constraints | ✅ Complete — pushed (f8b79b7..4461ab9); see Section 14 |
| H — Tests | H1 | Unit tests | ✅ Complete — pushed (193b42b); see Section 15 |
| H — Tests | H2 | Connector contract tests | ✅ Complete — pushed (def4cd8); see Section 15 |
| H — Tests | H3 | Database integration tests | ✅ Complete — pushed (78ce177); see Section 15 |
| H — Tests | H4 | API tests | ✅ Complete — pushed (f0578e9); see Section 15 |
| H — Tests | H5 | E2E + idempotency + failure recovery tests | ✅ Complete — pushed (4de3436); see Section 15 |
| I — Verification | I1 | Full acceptance scenario (spec Section 20, steps A–O) | ✅ Complete — pushed (99f4f75); see Section 16 |
| I — Verification | I2 | README completion | ✅ Complete — pushed (fff40f6); see Section 16 |

**Total: 26 tasks across 9 phases. All 26 are complete; the task map defines no task after I2.**

Release state: `origin/main` is `945e0bb`. All of A1–I2 is pushed, including the I-phase commits
(`99f4f75..945e0bb`). The Layer 1 task map is closed. Local `main` carries unpushed commits ahead
of it: the post-Layer-1 strategy, the VS-01 plan and the M0 reports, which touch no code, **and
the VS-01 milestones M1, M2 and M3, which do**. Layer 1 itself remains frozen — those milestones
add packages under `app/intelligence/` and `app/relationships/` and change no Layer 1 module,
migration, route or dataset row.

**M0 (Layer 2 pre-flight) completed 2026-09-19** — see Section 18. VS-01 is **in progress**:
M1, M2 and M3 are complete and the next unit of work is **milestone M4**.
`CONTEXT/VS01_IMPLEMENTATION_PLAN.md` carries the per-milestone status table, and it is the
single authority for which milestone is done — this section does not restate it.

---

## 13. Source Documents

- `CONTEXT/INTRODUCTION/AI_CEO_Project_Proposal.pdf`
- `CONTEXT/INTRODUCTION/AI CEO - Review 1 Presentation.pptx`
- `CONTEXT/Layer1_Prompt/AI_CEO_Layer_1_Master_Build_Prompt.pdf` (Sections 2–23 are the engineering spec)

---

## 14. Phase Record — G2 (Secret hygiene audit + security constraints)

**Scope source**: spec Section 14 (Security and Safety), the Section 15 "Security" test layer ("Secrets not returned/logged; invalid configuration rejected"), Section 10 ("Do not expose connector secrets"), and the Section 21 anti-pattern "Secrets in .env committed to Git".

**Out of scope, unchanged**: authentication (none, by design for the prototype), D1/D2 semantics, E1 persistence and status semantics, F1/F2 contracts, G1 metric and logging semantics, and Docker files.

| Milestone | Commit | What it adds | Tests | Mutation |
|---|---|---|---|---|
| M1 | `f8b79b7` | `app/core/security.py`: URL, path and timeout validation; GET-only, same-origin, no-redirect client; Odoo mock and REST connectors use it | 158 | 57/57 killed |
| M2 | `2761d50` | CSV file-name, directory-containment (symlinks) and size-limit checks at config parse and at every read | 70 | 36/36 killed |
| M3 | `b461c58` | `scripts/secret_scan.py` + `make secret-scan`; `Settings` repr hides credentials; `get_engine` never echoes SQL and hides parameters; static security boundary tests | 111 | 84/84 killed (2 first-run survivors were real test gaps, fixed) |
| M4 | `e9e08bf` | End-to-end secret canary integration test; README "Security (G2)" section | 5 | 10/10 injected leaks killed |

**Design decisions**
- Rejection messages name the broken rule, never the configured value (URLs can embed credentials).
- The read-only client re-checks every request, so a code path that bypasses configuration validation still cannot write or reach another host.
- CSV files are re-checked at read time, so directly constructed configurations, symlinks and oversized files are refused too.
- The secret scan never prints matched values (fingerprints only); synthetic test fixtures are pinned by path, rule and fingerprint rather than by widening the rules.
- Integration changes to released code were narrow: C2, C4 and C5 config parsing and client construction; `app/core/config.py` and `app/core/database.py`; the Makefile. Valid configurations behave as before.

**Verification at `e9e08bf`**: full suite 3462 passed; ruff 69 findings (baseline 71; two pre-existing B904 removed on replaced lines); mypy 9 errors (baseline 9); secret scan 0 findings over 208 tracked text files.

**Known limitations**
- No host allowlist: URL validation is structural.
- CSV health checks and entity discovery only check that files exist; the containment and size checks run when files are read.
- The secret scan is heuristic: tracked text files only (not git history or PDF/PPTX); generic rules skip values under 8 characters or marked as placeholders, and may report a long non-secret value assigned to a secret-named variable.
- Canonical business fields are returned as ingested; a credential stored in a source business field is data and is exposed by the entity API.

---

## 15. Phase Record — H (Tests)

**Scope source**: spec Section 15 (Testing Requirements), whose minimum-coverage
table names the layers H1–H5 implement. Section 20's acceptance scenario is I1's
scope and was not executed here; H covers the automated test layers only.

**Out of scope, unchanged**: D1/D2 semantics, E1 persistence and status
semantics, F1/F2 contracts, G1 metric and logging semantics, G2 security
behaviour, and all Docker files. No production behaviour was changed in H.

| Task | Commit | What it adds | Tests | Mutation |
|---|---|---|---|---|
| H1 | `193b42b` | Unit coverage of the normalization loader, validation classifier, connector page contract, pagination helper and repository guards the D1/D2/E1 suites cannot reach | 99 | 33/33 killed (1 equivalent excluded) |
| H2 | `def4cd8` | One contract suite run against all three real connectors over the same demo dataset, plus their configuration and failure paths | 185 | 26/26 killed |
| H3 | `78ce177` | Migration pipeline and schema parity on a private database; constraints, FK delete rules, upsert identity and run tracking | 102 | 12/12 killed |
| H4 | `f0578e9` | Cross-route API contract discovered from the OpenAPI document: correlation, envelope, read-only verbs, pagination, disclosure | 65 | 16/16 killed |
| H5 | `4de3436` | End-to-end over HTTP, idempotency over the API's own view, and failure recovery for malformed rows, network, database and partial-batch failures | 60 | 6/6 killed |

**Design decisions**
- Test layers are selected by path, not by marker: the `unit` marker predates H
  and covers only a few modules. `contract`, `integration` and `e2e` are applied
  consistently by the new suites.
- The connector contract suite builds the three real connectors over the same
  committed CSVs (served directly and through the in-process C3 mock-source), so
  interface drift between connectors is detectable. Read-only behaviour is proved
  three ways: method names, static inspection, and the mock-source request log.
- The migration suite owns a private `<database>_migrations_test` so it can build
  and drop the schema repeatedly without disturbing the shared E1 database.
- The API suite discovers routes from the application's own OpenAPI document, so
  a route added later is covered without editing the suite.
- The end-to-end suites inject the connector provider, because the API
  deliberately refuses a data directory or base URL from a request. That keeps
  the API contract intact while still allowing the bad fixture and injected
  failures to be driven through HTTP.
- The only integration change to released code was moving the PostgreSQL harness
  from `tests/integration/conftest.py` to `tests/conftest.py` so the end-to-end
  suite shares it. Its behaviour is unchanged and the integration suite still
  passes unmodified.

**Verification at `4de3436`**: full suite 3973 passed; `app/` line coverage 100%
(0 uncovered lines, up from 98% / 87 uncovered at `4461ab9`); ruff 69 findings
(baseline 69); mypy 9 errors (baseline 9); secret scan 0 findings over 220
tracked text files.

**Known limitations**
- Mutation testing uses an ad-hoc textual harness, not a mutation framework, so
  the mutant set is chosen rather than exhaustive.
- One equivalent mutant is excluded and documented: removing the type check in
  `_optional_decimal` is unobservable, because `Decimal(str(value))` raises
  `InvalidOperation` with the identical message for every YAML-reachable value
  the check rejects.
- The `unit` pytest marker remains inconsistent across the pre-H unit suite;
  retrofitting it was out of scope for H.
- Coverage is line coverage. Branch coverage was not measured.

---

## 16. Phase Record — I (Layer 1 Acceptance & Documentation)

**Scope source**: spec Section 20 (the full-performance acceptance test, steps
A–O and its twelve acceptance thresholds), Section 11, which reserves
`scripts/verify_layer1.py`, and Section 17, which lists the required command
surface and what the README must contain. Section 21's "Claiming production
readiness → call it a prototype and document limitations" governs the
limitations section.

**Out of scope, unchanged**: D1/D2 semantics, E1 persistence and status
semantics, F1/F2 contracts, G1 metric and logging semantics, G2 security
behaviour, H's test layers, and all Docker files. **I changed no production
code**: nothing under `app/`, `config/`, `migrations/` or `data/` differs
between `a3f5eba` and `fff40f6`.

| Task | Commit | What it adds | Tests | Mutation |
|---|---|---|---|---|
| I1 | `99f4f75` | `scripts/verify_layer1.py` and a real `make verify-layer1`: the Section 20 scenario as ten named checks, each with a pass condition and a line of observed evidence | 135 | 49/49 killed (6 first-run survivors were real test gaps, fixed) |
| I2 | `fff40f6` | README Architecture, Running Locally, Acceptance Checklist, Troubleshooting and Known Limitations, plus tests that validate every README claim against the code | 30 | 18/18 killed (2 first-run survivors were weak assertions, strengthened) |

**Design decisions**
- The acceptance command drives a **running stack over HTTP**, so its report
  describes the deployed system rather than re-testing the code in process.
  Readiness, source health, canonical records, runs and errors are read through
  the published API; ingestion is started with `POST /ingestion/runs`.
- The one crossing is steps K–L. The API deliberately refuses a data directory
  from a request (a G2 property), so the malformed fixture goes through the same
  `run_ingestion()` entry point the API and `scripts/ingest_demo.py` use, and is
  then read back through the API — which doubles as a check that the command and
  the API are on one database.
- The command **observes; it does not re-implement**. Migration proof stays in
  H3, connector read-only proof in H2, route contracts in H4, failure recovery
  in H5. That is why no production code changed: every behaviour the scenario
  asserts already existed and was reachable through an existing interface.
- Steps N and O are reported as operator steps rather than faked. N (the full
  suite) runs only with `--with-tests`, because it needs its own database; O (a
  clean rebuild) cannot be done by a script talking to the stack it would tear
  down.
- The command writes only through ingestion, so repeating it is a `NOOP`. It
  never deletes or edits rows.
- README claims are **tested, not asserted**: `tests/unit/test_i2_readme.py`
  recomputes every count the README quotes (tests per layer, dataset rows, ruff
  findings, mypy errors) and checks every make target, script, route, error
  code, option table, query parameter and internal link against the code.
- Two named, justified G2 boundary exemptions were added for the acceptance
  script — it builds an `httpx.Client` for Layer 1's *own* API (where starting a
  run is a POST, so the read-only client cannot serve it) and runs `pytest` in a
  subprocess for step N. The rule was not weakened for any other module, a test
  requires an exemption that is no longer needed to be removed, and another pins
  that the only non-GET request the scenario makes is `POST /ingestion/runs`.
- Three pre-existing defects were fixed because the scenario depends on them:
  `make secret-scan` was declared and documented since G2 but had no recipe, so
  it silently did nothing; `make migrate` and `make migration-status` called a
  bare `alembic`, failing without an activated virtualenv while every other
  target used `.venv/bin`; and `tests/integration/test_b1_database.py` opened
  the configured development database, so it failed as soon as step E had
  ingested the demo dataset into it — precisely the state step N runs in. Each
  is now pinned by a test.

**Verification at `fff40f6`**: full suite 4139 passed (I tests 165: I1 135, I2
30); `app/` line coverage 100% (4460 statements, 0 uncovered); I mutation audit
67 mutants, 67 killed; ruff 69 findings (baseline 69); mypy 9 errors (baseline
9); secret scan 0 findings over 224 tracked text files; `make verify-layer1`
exits 0 (8 passed, 0 failed, 1 skipped, 1 operator). Determinism and idempotency
were verified against the running stack: a clean rebuild with an empty database
reproduced the same report, the evidence that does not depend on run history is
byte-identical across runs, canonical ids are stable, a repeated run inserts and
updates nothing, and all seven canonical entity types hold one row per source
identity. The D1–D2, E1–E2, F1–F2, G1–G2 and H1–H5 regression groups all pass.

**Known limitations**
- The acceptance command needs a running stack **and** a reachable
  `DATABASE_URL`, and must be run on the host: the API image deliberately
  excludes `data/fixtures/`, which steps K–L read.
- Steps N and O are not performed by the command, by design; the report names
  them as operator steps rather than counting them as passed.
- `tests/unit/test_i2_readme.py` recomputes the counts the README quotes, so
  adding any test fails that check until the README's per-layer table and totals
  are updated. This is deliberate — it is what stops the README drifting — but
  it makes the README part of the cost of adding a test.
- Mutation testing still uses the ad-hoc textual harness described in Section
  15, so the mutant set is chosen rather than exhaustive.
- Coverage is line coverage; branch coverage was not measured.

---

## 17. Post-Layer-1 Strategy (VS-01 in progress; VS-02 onward PLANNED)

**Decided 2026-09-18** after a repository and dataset audit, a strategy grilling, a second
grilling of VS-01, and a third adversarial review that rebuilt the VS-01 plan as v2. The full
reasoning lives in the two companion documents; this section records only the state and the
bindings that apply to all future work.

| Document | Contents | Status |
|---|---|---|
| `CONTEXT/AI_CEO_POST_LAYER1_STRATEGY.md` | Vertical-slice rationale; measured Layer 1 capability; data-feasibility verdict; graph / RAG / ML / agent / governance strategy; VS-01–VS-08 roadmap; deferred-infrastructure triggers; future data requirements; grilling record | PLANNED / PROPOSED |
| `CONTEXT/VS01_IMPLEMENTATION_PLAN.md` | **v2.3.** Section 0 records the sixteen defects the adversarial review found, and §0.1–§0.2 the M2/M4 boundary and the M3 closure; specification A1–A31; milestones M1–M9 with objective, before/change/after, tests, acceptance and non-goals | IN PROGRESS — M1–M3 complete; see its status table |
| `CONTEXT/M0_BASELINE_REPORT.md` | The measured Layer 2 pre-flight baseline and findings F1–F8 | COMPLETE — see Section 18 |
| `CONTEXT/M0_CLOSURE_REPORT.md` | F1 root cause, the F2 fingerprint decision, F3–F9 verification, corrections and M1 entry conditions | COMPLETE — see Section 18 |

### 17.1 Slice sequence

VS-01 Customer Risk & Executive Escalation (**in progress**) → VS-02 Revenue & Pipeline Intelligence
(introduces FX normalization) → VS-03 Executive Account 360 → VS-04 Cross-Functional CEO
Decision → VS-05 Enterprise Copilot. Then, **FUTURE / CONDITIONAL**: VS-06 Longitudinal
Analytical Projection → VS-07 Churn Modelling → VS-08 Revenue Forecasting.

VS-01 owns **conflict detection, a versioned conflict policy and recorded dissent**. VS-04
therefore extends an existing mechanism (three or more functions, cyclic conflicts, model-
generated narrative over an already-decided action) rather than inventing it.

### 17.2 Measured facts that bind every future slice

Established by reading the code and data on 2026-09-18, not by reading earlier documents:

- **Only three canonical FKs to `customers` exist** (`deals`, `projects`, `support_tickets`).
  The only other canonical entity→entity FK is `employees.organization_id → organizations.id`.
  Owner, assignee and manager relationships are `source_id` strings joined within one source
  system. `documents` carries **no** customer reference at all.
- **No cross-source entity resolution.** All intelligence must be scoped to one declared
  `source_system`, or the same customer is counted once per connector.
- **The dataset clock is frozen at 2026-08-27.** A 14-day window measured from a `now()` of
  2026-09-18 contains zero tickets. Hence the `as_of` rule in Section 5.
- **Exactly one customer (CUST-007) satisfies DOC-003's documented escalation rule** — three or
  more tickets in any 14-day window. This is the foundation of the VS-01 demo, and it is a
  document-grounded policy rule rather than an invented threshold.
- **Risk and money must stay on separate axes.** CUST-007 is first on support pressure but
  **22nd of the 23 customers holding active deals** on weighted exposure; within USD alone its
  weighted exposure is exactly the median of 7 USD customers. No cross-currency ranking is
  computable until VS-02 delivers FX, so the two must never be compared as one number. A blended
  score would surface the wrong customer.
- **Mixed currency with no FX table** (INR 30 / USD 13 / EUR 1). No cross-currency aggregate may
  be produced until VS-02 delivers the rate set.
- **Churn and forecasting are not defensible on the current data.** All 4 inactive customers have
  zero tickets and zero deals; there is no `lost` deal stage, so no negative class; 14 `won`
  deals over 8 distinct months is not a series. Hence the VS-06 analytical projection.

### 17.3 Bindings that carry across all slices

1. Layer 1 stays frozen. Its D1 vocabulary is never widened to satisfy an analytical need.
2. No module in an intelligence, analyst or decision package may call `now()`.
3. No slice from VS-01 to VS-05 contains an **executor**. Nothing can send, write or call out.
   Enforced by a static boundary test in the G2 style.
4. Approval binds to a brief's **content hash**, and decision rows are append-only.
5. Authentication is a hard prerequisite before any executor is ever built. Until then an
   approver identity is *asserted*, not verified, and must be documented as such.
6. Every asserted fact in generated output carries a resolvable citation to a canonical
   record+field or a document id+span.
7. No churn probability or forecast may ever be attached to a demo customer by name.
8. No datastore is introduced without a slice whose question requires it.

### 17.4 Open decisions

1. **Proposal §9 reconciliation.** The proposal commits to a churn model and a revenue forecast
   validated against a held-out baseline. The VS-06 → VS-07/VS-08 route can satisfy that
   honestly, but only on synthetic data with the framing in strategy §6.6. Whether that framing
   is acceptable is a decision for the project guide and should be raised early.
2. **Frontend scope.** The proposal promises a React copilot interface; no slice before VS-05
   has been shown to need a UI beyond OpenAPI.
3. **Language-model provider** for VS-04/VS-05 — deferred by design.
4. **Authentication timing** — not needed for VS-01–VS-05, required before any executor.

### 17.5 VS-01 v2 — what the adversarial review changed

v1 of the VS-01 plan was attacked deliberately; sixteen defects were found and the plan was
rebuilt. The full list is Section 0 of `CONTEXT/VS01_IMPLEMENTATION_PLAN.md`. The six that
changed the design:

| Defect | Why it mattered | Resolution |
|---|---|---|
| **VS-01 did not prove the concept.** Two analysts that never disagree produce a report, not a reconciliation | The platform's thesis is that fragmented functional signals are reconciled into one executive decision. Nothing was being reconciled | Conflict reconciliation moved into VS-01. Sales reads DEAL-001 as a 90% negotiation to accelerate; Support reads an active DOC-003 escalation with three open high-priority tickets past SLA target and wants deal pressure paused; DOC-009 records the customer tying the deal to those tickets. Two incompatible actions on one object |
| `open_high_priority_count` stated as **4**; it is **3** | TKT-073 is high priority but resolved. The dataset has 4 high-priority tickets and 4 open tickets — different sets of 4 | Split into `open_high_priority_count` (3) and `high_priority_total` (4), each pinned by a test |
| The `as_of` default contradicted the asserted values | Default resolves to `max(created_at)` = 2026-08-27, but every value was computed at 2026-09-18. **At the 2026-08-27 default** the SLA-breach ranking differs (CUST-009 has 4, CUST-007 has 3); at 2026-09-18 CUST-007 leads with 5 | Acceptance pins `ACCEPTANCE_AS_OF = 2026-09-18`; the `max(created_at)` fallback is for ad-hoc use only |
| Idempotency was silently wrong | Keyed on `(customer_id, as_of, rules_version)`, a re-run after new ingestion would hit the unique constraint and serve **stale intelligence with no error** | `layer1_fingerprint` is part of the assessment row and its uniqueness; a fingerprint-sensitivity test pins it |
| Approval bound to the rendered brief | One whitespace change in a template would invalidate every prior approval | Approval binds to the decision **payload** hash; prose is a view |
| Analyst scope isolation was advisory | Analysts were to receive a SQLAlchemy `Session`, and anything holding a session can read any table | Analysts receive typed context objects and no session; a context-purity test replaces a convention |

**Milestone consequence:** M6 (conflict detection and reconciliation) is the milestone that must
not be cut. Without it VS-01 is a report with citations; with it, it is a proof of the
platform's thesis and the mechanism VS-04 extends.

**Foundations VS-01 establishes**, each with the slice that first consumes it: `Scope`
(`as_of`, `source_system`, `layer1_fingerprint`) — every slice; relationship model with
per-edge basis — VS-02/03/04/05; evidence and citation contract — every slice;
`AnalystContext` → `Position` — VS-04/05; `ConflictPolicy` + reconciler — VS-04;
`ActionCatalogue` — VS-03/04; payload-bound `DecisionRecord` — VS-03/04; `MoneyValue`
(currency-qualified, never summed) — VS-02, where FX plugs in without touching a VS-01 call
site.

---

## 18. Phase Record — M0 (Layer 2 pre-flight baseline and closure)

**Decided 2026-09-19.** M0 is a pre-flight phase, not a milestone: it establishes a
scientifically reproducible starting line for Layer 2 and resolves everything that would
otherwise be encoded wrongly in VS-01 code. **No production code, test, migration, schema,
config, dataset or Docker file was changed in M0.**

| Document | Contents |
|---|---|
| `CONTEXT/M0_BASELINE_REPORT.md` | The measured baseline: Git, Layer 1 contracts, dataset, vocabulary, schema, API, tests, quality, security, deployment, VS-01 readiness, frozen invariants, findings F1–F8 |
| `CONTEXT/M0_CLOSURE_REPORT.md` | F1 root cause and options; the F2 fingerprint decision; F3–F9 verification; the exact corrections; grilling record; M1 entry conditions |

**Baseline confirmed** (all matching the `fff40f6` Layer 1 record): 4139 tests passed, `app/`
line coverage 100% over 4460 statements, ruff 69, mypy 9, secret scan 0 findings, Alembic head
`8bfd73b6af60`, 22 API operations, 233 canonical dataset rows. Every VS-01 signal value S1–S15
at `as_of` 2026-09-18 was independently recomputed from `data/demo/` and verified correct.

### 18.1 F1 — the development database lifecycle · CLOSED

The development database was found holding 220 rows over five entity types, with zero
`organizations` and zero `documents`, plus four malformed-fixture rows inside the `csv_demo`
scope. **This was not a defect.** It is the residue of `make verify-layer1`, which by
specification (Section 20 step E) ingests only `customers`, `employees`, `deals`, `projects` and
`support_tickets`, and then ingests the malformed fixture through the `csv_demo` connector so
that step L can read the surviving rows back through the public API.

**Resolution — A + D, adopted.** Layer 1 stays frozen; no new `source_system` is introduced.

1. **The clean Layer 2 starting state comes from the full seven-entity path**: empty database →
   `make migrate` → `make ingest-demo` with **no `--entities` filter** → 233 rows across 7 entity
   types, 0 rejected, `SUCCESS`; a repeat run is `NOOP`.
2. **The pinned `layer1_fingerprint` is the guard.** VS-01 compares the computed fingerprint
   against the pinned value and refuses to assess on a mismatch, so a `verify-layer1` residue
   fails loudly instead of silently producing a citation-free brief.

`make verify-layer1` remains the correct, unchanged **Layer 1** acceptance command. It must not
be used to prepare a VS-01 evaluation database.

**Rejected:** isolating the fixture under a `csv_demo_bad` source system. It would widen the D1
`source_systems` vocabulary — which binding 1 of §17.3 forbids — and would require rewriting the
I1 acceptance tests.

### 18.2 F2 — `layer1_fingerprint` composition (v2) · CLOSED

Layer 1's `record_hash` covers business fields only and **excludes all provenance, including
`source_id`**. A fingerprint over `record_hash` values and counts alone is therefore blind to
every `source_id` rename — measured, not assumed — while `source_id` is the join key for every
`SOURCE_KEY_JOIN` edge, the input to `canonical_id`, what E1 resolves the customer FKs against,
and the token quoted in `ID_TOKEN` links and citations.

**Adopted: fingerprint v2**, specified in full at `CONTEXT/VS01_IMPLEMENTATION_PLAN.md` §A5.1.

- **Composition:** SHA-256 over `{entity_type: {"count": n, "records": [[source_id, record_hash], ...]}}`
  for the seven canonical entity types in scope, serialised with `record_hash`'s own discipline
  (`sort_keys=True`, `separators=(",", ":")`, UTF-8).
- **Ordering:** each list read with an explicit `ORDER BY source_id`.
- **Excluded:** `ingested_at`, `ingestion_run_id`, `source_updated_at` — they change on every
  ingestion, and including them would defeat the idempotency the fingerprint protects.
- **Detects:** business-content changes, `source_id` renames (including order-preserving ones),
  and `source_id` additions or removals.
- **Layer 1 untouched:** this is a Layer 2 composition over two frozen Layer 1 columns. No change
  to `record_hash`, no Layer 1 module, no migration, no vocabulary change.
- **Determinism:** byte-identical across independent clean rebuilds. For the committed demo
  dataset at `source_system='csv_demo'` the value is
  `1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00`.

### 18.3 F3–F9 — corrections applied

| # | Correction | Affected a named test? |
|---|---|---|
| F3 | Weighted exposure restated currency-qualified: CUST-007 is **22nd of 23** on weighted exposure, not "roughly twelfth"; the ~327,750 median is mixed-currency and must not be compared with a USD amount | no |
| F4 | The SLA-breach ranking "CUST-009 has 4, CUST-007 has 3" belongs to **2026-08-27**, the `max(created_at)` default — not to the pinned 2026-09-18, where CUST-007 leads with 5 | no |
| F5 | "Evergrid Textiles" (CUST-039) added wherever the substring trap is enumerated — the dataset holds **four** "Textiles" customers, not three | yes — §A25 test 7 |
| F6 | Ticketless customers are **15 in total**, of which the 4 inactive ones are a subset (11 active + 4 inactive), not 15 + 4 | yes — §A25 test 10 |
| F7 | Stated explicitly that **no VS-01 signal is derived from any document link**; all signals come deterministically from canonical rows, and §A25 test 4 must keep asserting exact equality of every signal value | no |
| F8 | Stale metadata corrected: this document's date; A3's "11 migrations"; "only three canonical FKs" (three *to customers*; `employees.organization_id` is a fourth); I1/I2 push status; `brief_content_hash` → `payload_hash`; and the plan's own M0 instruction, which told the reader to run `make verify-layer1` — the very cause of F1 | no |
| F9 | `escalation_path(CUST-007)` returns **all four** open-ticket assignees EMP-017/018/020/021 → EMP-004. EMP-017 owns the open `medium` billing ticket TKT-079 and must not be filtered out; §A9 says *each open ticket's* assignee | yes — M2 |

### 18.4 M1 entry conditions — satisfied

| Condition | Evidence |
|---|---|
| E1 — development database rebuilt via the full seven-entity path | 233 rows across 7 entity types, 0 rejected, `SUCCESS`; repeat run `NOOP` with 233 unchanged; 0 fixture rows; 0 ingestion errors; single `source_system` `csv_demo` |
| E2 — fingerprint composition decided and recorded | §18.2 above and `VS01_IMPLEMENTATION_PLAN.md` §A5.1, §A25 test 13b, M1 |
| E3 — all documentation and specification corrections applied | §18.3 above; the six test-bearing corrections are in §A11, §A23, §A25 tests 7/10/13b, §A27.1–1b, §A28, M1 and M2 |
| Layer 1 freeze re-verified | `data/demo/` fingerprint, `normalization.yaml`, Alembic head `8bfd73b6af60` and the canonical UUID5 namespace all unchanged; nothing under `app/`, `tests/`, `migrations/`, `config/`, `data/` or the Docker files was modified |

**M1 may begin.** It is the first milestone of `CONTEXT/VS01_IMPLEMENTATION_PLAN.md` Part B and
creates only `app/intelligence/` foundations — no signals, no persistence, no API.

---

## 19. Phase Record — M9 (VS-01 acceptance, evaluation and hardening)

**Scope.** M9 turns VS-01 into one reproducible command and proves its claims rather than
asserting them. It changes no production code, configuration or migration. It adds:

- the acceptance command `make verify-vs01` (`scripts/vs01_acceptance.py`);
- the §A26 fixture package (`tests/fixtures/vs01/`);
- the §A25 proof corpus and its one missing proof;
- the end-to-end scenario test;
- the mutation audit and the tests it found missing;
- three dependency pins;
- the README's VS-01 section.

Layer 1 and M1–M8 behaviour are frozen: every file under `app/`, `config/`, `migrations/`,
`data/` and `tests/golden/`, and the Docker files, are byte-identical to their anchors.

### 19.1 Specification

`CONTEXT/VS01_IMPLEMENTATION_PLAN.md` §0.8 is M9's authoritative specification, committed alone as
`79f8d9e` ("M9: finalize specification"). It resolves:

- three contradictions with frozen tests:
  - K1, the pinned run: one named Layer 2 importer, `scripts/vs01_acceptance.py`;
  - K2, G2's exemptions: one named module;
  - K3: §A27.10 means regression against the authorised evolved test baseline;
- twelve ambiguities, A1–A12;
- six review items, R-M9-1…R-M9-6:
  - R-M9-1: an isolated acceptance database, and no fallback to the development stack;
  - R-M9-2: A27.9 before A27.8, and A27.8 as the last write;
  - R-M9-3: `pyproject.toml` is authoritative for three pins;
  - R-M9-4: M9-owned fixture proofs;
  - R-M9-5: the binary mutation rule;
  - R-M9-6: A27.9's M8 semantics.

The test evolution is exactly T-M9-1…T-M9-5.

### 19.2 Implementation milestones

| Commit | Phase | What it adds |
|---|---|---|
| `7a410a5` | 2 | `M9: add the VS-01 fixture package` — `tests/fixtures/vs01/` (manifest, loader and guard, five delta directories) and `tests/integration/test_vs01_fixtures.py` (71) |
| `c50ecb4` | 3 | `M9: pin the dependencies acceptance depends on` — `sqlalchemy>=2.0.0,<2.1`, `ruff==0.16.7`, `mypy==2.3.1` in `pyproject.toml` |
| `a801ce7` | 3 | `M9: add the VS-01 acceptance command` — the script, `make verify-vs01`, `tests/unit/test_vs01_acceptance.py`, T-M9-1…T-M9-3 |
| `5c05f68` | 4 | `M9: prove the VS-01 scenario end to end` — `tests/e2e/test_vs01_scenario.py` (5) |
| `e643d27` | 5 | `M9: close the §A25 scope-leakage gap` — T-M9-4; the §A25 test 10 proof `tests/integration/test_vs01_a25_closure.py` |
| `0769441` | 6 | `M9: close the mutation audit's test gaps` — `tests/integration/test_vs01_mutation_closure.py` (23) |
| — | 7 | `M9: document the VS-01 slice` — the README's VS-01 section, T-M9-5, this record |

### 19.3 Verification — each gate

Every gate ran the full suite with the lint caches outside the repository, and measured `app/`
coverage, ruff, mypy, the secret scan (tracked and untracked files), the head, the frozen-path diff
and the strategy document's diff. Each gate is green:

- 0 failed and 0 skipped;
- coverage 100% over 7456 statements;
- ruff 69, the same finding set as `2b6deb3`;
- mypy 9;
- secret scan 0;
- one head, `070e4968a497`;
- the golden file `87d13986…9dce`;
- the strategy diff `94e4e5b2…`.

| Gate | Tests (unit / contract / integration / e2e) |
|---|---|
| Phase 1 baseline (`79f8d9e`) | 6438 (5054 / 185 / 1119 / 80) |
| Phase 2 (`7a410a5`) | 6509 (5054 / 185 / 1190 / 80) |
| Phase 3 (`a801ce7`) | 6737 (5282 / 185 / 1190 / 80): the full run measured 6736, and the unit and contract layers were re-run (5467) after the falsifiability check added one unit test |
| Phase 4 (`5c05f68`) | 6742 (5282 / 185 / 1190 / 85) |
| Phase 5 (`e643d27`) | 6743 (5282 / 185 / 1191 / 85) |
| Phase 6 (`0769441`) | 6766 (5282 / 185 / 1214 / 85) |

Live runs of `make verify-vs01` in the developer `.venv` are development checks, not evidence of
record. Each exited 0 with 10 `PASS`, A27.10 `SKIPPED` and A28.citations `OPERATOR`. Around each
one, the development database (`8bfd73b6af60`, 233 rows) kept its revision and every table's row
count. §A25 test 10's clause "which include all 4 inactive ones" was asserted by no mapped test;
Phase 5 added the proof, and the corpus is now 31 node ids, collecting 44 tests.

### 19.4 Mutation result (§0.8.12, R-M9-5)

The audit used 274 mutants, fixed before the first run (sha256 `995517d0…d8cd8a`). The harness is
the ad-hoc textual one. For every mutant:

- the anchor matched exactly once;
- one mutant was applied at a time;
- pytest `-x` ran the target's kill set: its milestone's unit and integration files, then the §A25
  corpus;
- `PYTHONDONTWRITEBYTECODE` was set, with a per-mutant `PYTHONPYCACHEPREFIX`;
- the file was restored and its sha256 checked against its Phase 1 value.

The environment was the developer `.venv`: Python 3.11.5, SQLAlchemy 2.0.54, pytest 9.1.1, on the
suite's own `_test` database.

| Target | Mutants | Killed | Killed by a newly authorised test | Equivalent | Malformed |
|---|---|---|---|---|---|
| Signal engine (`signals.py`, `windows.py`, the signal inputs of `risk_rules.yaml`) | 87 | 65 | 14 | 8 | 0 |
| Risk-band table (`bands.py`, the band table) | 58 | 54 | 4 | 0 | 0 |
| Conflict policy (`conflict_policy.yaml`, `policy.py`, `conflicts.py`, `reconciler.py`) | 97 | 93 | 2 | 2 | 0 |
| Linker (`linker.py`) | 32 | 25 | 3 | 4 | 0 |
| **Total** | **274** | **237** | **23** | **14** | **0** |

No mutant was killed only under a named condition. The 23 new tests are in
`tests/integration/test_vs01_mutation_closure.py`, and each fails on its mutant. The gaps they close
are:

- closed-window boundaries;
- DOC-003's medium target and its three-ticket threshold, at their exact values;
- documented orders;
- band rows no demo customer sits on alone;
- zero thresholds the loaders must accept;
- public projections, and configuration arguments no production caller passes;
- an empty needle.

Each of the 14 equivalent mutants has a written proof, recorded verbatim in Part B M9's closure
block. **No survivor exposed a production defect**, and after the audit every target file's sha256
equals its Phase 1 value.

### 19.5 Acceptance result — the run of record (Phase 8)

Phase 7's gate, on the tree committed as `17de05f`, measured 6771 tests (5287 / 185 / 1214 / 85),
0 failed and 0 skipped. Every other §19.3 measurement was unchanged, but the gate reported three
warnings, not two (§19.6). Phase 8 made no commit and changed no file.

- **Environment.** A fresh virtual environment, installed from the pinned `pyproject.toml`
  (`pip install -e ".[dev]"`, Python 3.11.5), never the developer `.venv`. It resolved
  SQLAlchemy 2.0.54, ruff 0.16.7 and mypy 2.3.1. Eight unpinned packages resolved newer than in
  the developer `.venv`, each within its declared bound; among them are starlette 1.7.0 and
  uvicorn 0.54.0.
- **Two runs.** `scripts/vs01_acceptance.py --with-tests`, the recipe of
  `make verify-vs01 ARGS="--with-tests"`, ran twice. Both exited 0 with
  `11 passed, 0 failed, 0 skipped, 1 operator`, and the two reports are byte-identical:

```
verify-vs01: A27.1         clean_dataset        PASS      sqlalchemy 2.0.54; head 070e4968a497; organizations 1, employees 24, customers 50, deals 44, projects 22, support_tickets 80, documents 12; 233 fetched, 0 rejected: SUCCESS then NOOP
verify-vs01: A27.1b        pinned_fingerprint   PASS      pinned 1d891b0b matched; deliberate mismatch refused, 0 rows written; 50 assessments, 3 briefs
verify-vs01: A27.2         single_escalation    PASS      50 assessments; CUST-007 alone is CRITICAL and executive-worthy
verify-vs01: A27.3         brief_facts          PASS      payload_hash e93c29cf; narrative equals the golden file (12474 bytes); the 10 facts of A27.3; 36 citations
verify-vs01: A27.4         no_active_project    PASS      no active project, in the payload and the narrative
verify-vs01: A27.5         conflict_and_dissent PASS      CONF-001 over DEAL-001: PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED wins; ACCELERATE_DEAL_CLOSE dissents with 3 citations
verify-vs01: A27.6         citations_resolve    PASS      80 distinct citations across 50 assessments and 3 briefs resolve; 3 cited spans read back exactly
verify-vs01: A27.9         approval_boundary    PASS      REJECTED recorded; a second decision without supersedes_id refused (409 SUPERSEDES_REQUIRED); APPROVED supersedes it; history of 2 in chain order; status DRAFT; append-only held; 3 writes, 6 risk operations
verify-vs01: A27.8         determinism          PASS      re-run 200: identical hashes, 0 rows; one extra ticket: pinned run refused, unpinned run 201 with 50 new assessments
verify-vs01: A27.7         named_tests          PASS      44 passed: A25 tests 1-14 and 13b
verify-vs01: A27.10        regression           PASS      6771 passed; coverage 100% over 7456 statements; ruff 0.16.7: 69; mypy 2.3.1: 9; secret scan 0; head 070e4968a497
verify-vs01: A28.citations hand_citations       OPERATOR  operator step: in data/demo/documents.csv, confirm DOC-003 [238, 330) reads "Customers raising three or more tickets within 14 days are escalated to their account owner."; DOC-009 [238, 333) reads "The customer tied the Meridian Textiles - Seat Expansion decision (DEAL-001) to resolving them."; DOC-003 states the escalation rule, and DOC-009 ties DEAL-001 to the tickets
verify-vs01: 11 passed, 0 failed, 0 skipped, 1 operator
```

- **Operator-only.** A28.citations prints DOC-003's and DOC-009's cited spans for the reviewer's
  hand check. The command proves that they resolve. Whether they mean what the brief claims is
  the reviewer's judgement, and this record states none.
- **Isolation.** The development database (`8bfd73b6af60`, 233 rows) kept its revision and every
  table's row count before, between and after the two runs.
- **The rebuilt image.** `docker compose build api` rebuilt the API image from the pinned
  `pyproject.toml`. A throwaway container of it pointed read-only at the acceptance database the
  second run left. It published exactly the six risk operations and the three writes, and listed
  CUST-007 as the one executive-worthy customer, once per fingerprint. It was removed afterwards.
- **The diff audit.** Every file changed since `2b6deb3` is in §0.8.13's allowed set, except
  `tests/integration/test_vs01_a25_closure.py` (§19.6, item 1).

### 19.6 Known deviations

1. **The §0.8.13 path omission.** Phase 8 identified that §0.8.13's explicit allowed-path table
   omitted `tests/integration/test_vs01_a25_closure.py`, despite §0.8.6 and §0.8.15 expressly
   authorising a new file for a missing §A25 proof. Owner ratification on 2026-09-27 resolves
   this internal specification omission and authorises the file for M9 closure. §0.8.18's
   criterion 17 therefore holds under that ratification, not as §0.8.13 was originally written.
   The proof stays in its own file, and §0.8.13's committed text is unchanged.
2. **§0.8.7's count.** §0.8.7 says the fixture package has six material entries, but its own
   table gives seven: five delta directories and two loaders. The package follows the table.
3. **The README count lines.** The Phase 2 instruction excluded README edits, but §0.8.15 lists
   the README count lines in Phase 2. The owner authorised exactly the three count updates that
   gate needed. Every later phase updated only its own count lines.
4. **A third warning at Phase 7.** Every gate from Phase 1 to Phase 6 reported two third-party
   deprecation warnings, and Phase 7's reported three. The third is pydantic's
   `UnsupportedFieldAttributeWarning`, inside the frozen M8 concurrency test
   `test_two_concurrent_identical_requests_converge_on_one_result_set`. It appears in about one
   of five isolated runs of that test against the frozen code. It is pre-existing thread-timing
   nondeterminism, not an M9 regression (owner ruling). The gate results stand as measured.
5. **The mutation kill sets.** They hold §0.8.6's thirty corpus node ids, not the thirty-first,
   which Phase 5 added after they were built. An added test can only kill more, so no survivor
   is hidden, and the fourteen equivalence proofs do not depend on the kill sets.
6. **A Docker environment incident (Phase 5).**
   - A shell heredoc executed the backtick spans of draft README text, and one of them started
     `make docker-up`. It was stopped about two minutes into the image build.
   - No container was recreated. The development database, the `.venv` and the repository were
     unchanged.
   - The local tag `finalyearproject-mock-source:latest` now names an image rebuilt from
     unchanged inputs, and the previous image record could not be restored.
   - The incident was reported to the owner. `CONTEXT/VS01_IMPLEMENTATION_PLAN.md` Part B M9
     records it in full.

### 19.7 Closure state

- **M9 is COMPLETE, and its plan is closed** by the documentation commit
  `docs: close M9 implementation plan`. That commit changes only
  `CONTEXT/VS01_IMPLEMENTATION_PLAN.md` (the M9 status row, §A29 and Part B M9's closure block)
  and this section.
- **Commits.** The specification is `79f8d9e`. The implementation is `7a410a5`, `c50ecb4`,
  `a801ce7`, `5c05f68`, `e643d27`, `0769441` and `17de05f`. The last is Phase 7's commit, which
  §19.2 shows as "—" because this record was written before it existed. Phases 1 and 8 were
  verification phases and made no commit.
- **Criteria.** Every §0.8.18 criterion holds, criterion 17 under the ratification in §19.6.
  T-M9-1…T-M9-5 are the only test evolution.
- **Frozen.** VS-01 (M1–M9) is frozen as committed: `app/`, `config/`, `migrations/` (one head,
  `070e4968a497`), `data/`, `tests/golden/`, the Docker files, the three pins, the acceptance
  command, the fixture package and the tests. A change to any of them reopens its milestone.
- **The environment M9 leaves.**
  - The development containers were never recreated. They still run their 2026-09-16 images,
    and that API image publishes no `/risk` route.
  - The development database is still at `8bfd73b6af60`, with its 233 clean rows.
  - Both `finalyearproject-*:latest` image tags now name rebuilt images, so recreating the
    containers would start them from those.
  - Migrating and recreating the development stack is the owner's decision, outside M9.
- **Limitations.** The plan's §A29 carries M9's six (§0.8.16), and the README's VS-01 section
  summarises them.
- **Next.** VS-02 has not started.
