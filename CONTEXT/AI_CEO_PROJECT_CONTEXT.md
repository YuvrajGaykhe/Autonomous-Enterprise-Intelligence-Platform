# AI CEO — Project Context Document
**Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
**Last updated: 2026-09-16 | Maintained by: Yuvraj Gaykhe**

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

**IMPORTANT**: Do not implement or design Layers 2–5 during Layer 1 work. Layer 2 begins only after Layer 1 passes its full acceptance criteria.

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
| A — Foundation | A3 | Alembic setup + all 11 migrations | ✅ Complete — pushed (4d7e524) |
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
| I — Verification | I1 | Full acceptance scenario (spec Section 20, steps A–O) | ✅ Complete locally — not pushed (99f4f75); see Section 16 |
| I — Verification | I2 | README completion | ✅ Complete locally — not pushed (fff40f6); see Section 16 |

**Total: 26 tasks across 9 phases. All 26 are complete; the task map defines no task after I2.**

Release state (2026-09-17): `origin/main` is `a3f5eba` (A1–H, pushed as a fast-forward from `4461ab9` on 2026-09-16 after a green release audit). I1–I2 are committed locally only (`99f4f75..fff40f6`) and await review before any push.

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
