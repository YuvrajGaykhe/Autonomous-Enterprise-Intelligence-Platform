# AI CEO — Project Context Document
**Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
**Last updated: 2026-09-06 | Maintained by: Yuvraj Gaykhe**

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
| A — Foundation | A1 | Repository scaffolding | ✅ In Progress |
| A — Foundation | A2 | Docker Compose + service definitions | ⏳ Pending approval |
| A — Foundation | A3 | Alembic setup + all 11 migrations | ⏳ Pending approval |
| B — Core Contracts | B1 | SQLAlchemy ORM models | ⏳ Pending approval |
| B — Core Contracts | B2 | Pydantic canonical schemas | ⏳ Pending approval |
| B — Core Contracts | B3 | Pydantic source schemas | ⏳ Pending approval |
| C — Connectors | C1 | Connector base interface | ⏳ Pending approval |
| C — Connectors | C2 | CSV connector | ⏳ Pending approval |
| C — Connectors | C3 | Mock-source HTTP server | ⏳ Pending approval |
| C — Connectors | C4 | Odoo mock connector | ⏳ Pending approval |
| C — Connectors | C5 | Generic REST connector | ⏳ Pending approval |
| D — Normalization | D1 | Normalization engine | ⏳ Pending approval |
| D — Normalization | D2 | Validation and quarantine engine | ⏳ Pending approval |
| E — Orchestration | E1 | Ingestion orchestrator | ⏳ Pending approval |
| E — Orchestration | E2 | Demo data generation | ⏳ Pending approval |
| F — API | F1 | FastAPI routes — health, sources, ingestion | ⏳ Pending approval |
| F — API | F2 | FastAPI routes — canonical entities + metrics | ⏳ Pending approval |
| G — Observability | G1 | Structured logging + ingestion metrics counters | ⏳ Pending approval |
| G — Observability | G2 | Secret hygiene audit + security constraints | ⏳ Pending approval |
| H — Tests | H1 | Unit tests | ⏳ Pending approval |
| H — Tests | H2 | Connector contract tests | ⏳ Pending approval |
| H — Tests | H3 | Database integration tests | ⏳ Pending approval |
| H — Tests | H4 | API tests | ⏳ Pending approval |
| H — Tests | H5 | E2E + idempotency + failure recovery tests | ⏳ Pending approval |
| I — Verification | I1 | Full acceptance scenario (spec Section 20, steps A–O) | ⏳ Pending approval |
| I — Verification | I2 | README completion | ⏳ Pending approval |

**Total: 26 tasks across 9 phases.**

---

## 13. Source Documents

- `CONTEXT/INTRODUCTION/AI_CEO_Project_Proposal.pdf`
- `CONTEXT/INTRODUCTION/AI CEO - Review 1 Presentation.pptx`
- `CONTEXT/Layer1_Prompt/AI_CEO_Layer_1_Master_Build_Prompt.pdf` (Sections 2–23 are the engineering spec)
