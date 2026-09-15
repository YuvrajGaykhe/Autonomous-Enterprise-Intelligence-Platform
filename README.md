# AI CEO — Layer 1: Connector and Ingestion Subsystem

> **Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
> Layer 1 of the AI CEO platform — the Connector Layer.

---

## Architecture

<!-- To be completed in Task I2 -->

---

## Prerequisites

- **Docker** and **Docker Compose** (v2) installed
- **Python 3.11+** (for local development without Docker)
- **Git**

---

## Environment Setup

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` with your values (the defaults work for local Docker development).
3. **Never commit `.env`** — it is gitignored.

---

## Database Migration

Layer 1 uses [Alembic](https://alembic.sqlalchemy.org/) for database schema management.

**Directory structure:**
```
alembic.ini              # Alembic config (DB URL is overridden at runtime)
migrations/
  env.py                 # Migration environment (reads from app.core.config)
  script.py.mako         # Migration script template
  versions/              # Migration files (committed to git)
```

**Run migrations (upgrade to latest):**
```bash
# Locally (with venv active and PostgreSQL running):
alembic upgrade head

# Via Docker:
docker compose exec api alembic upgrade head

# Via Makefile:
make migrate
```

**Check current migration state:**
```bash
alembic current
alembic history --verbose

# Via Makefile:
make migration-status
```

**Downgrade one revision:**
```bash
alembic downgrade -1
```

**Generate a new migration after model changes (B1+):**
```bash
alembic revision --autogenerate -m "describe_the_change"
```

> **Warning:** Do not run `docker compose down -v` unless you intend to destroy
> the PostgreSQL data volume. Use `docker compose down` (without `-v`) for
> normal stops.

---

## ORM Model Layer

Layer 1 uses SQLAlchemy ORM models organized in `app/persistence/models/`.

### Canonical Entity Tables (7)

| Table | Purpose | `is_active` |
|---|---|---|
| `organizations` | Enterprise boundary / tenant | No |
| `employees` | HR and ownership relationships | Yes |
| `customers` | Customer/account intelligence | Yes |
| `deals` | Sales/revenue intelligence | Yes |
| `projects` | Delivery/resource context | Yes |
| `support_tickets` | Risk/support signals | No |
| `documents` | Future RAG/institutional memory | No |

### Operational Tables (5)

| Table | Purpose |
|---|---|
| `ingestion_runs` | One row per execution; status, timing, counts |
| `ingestion_errors` | Structured rejected-record and connector errors |
| `source_records` | Raw/source payload + provenance + content hash |
| `connector_configs` | Non-secret connector configuration |
| `ingestion_cursors` | `(source_system, source_entity)` cursor state |

### Provenance Fields

Every canonical entity includes: `id` (UUID PK), `source_system`, `source_entity`,
`source_id`, `source_updated_at`, `ingested_at`, `ingestion_run_id`, `record_hash`.

**`record_hash`** covers only canonical business fields (excludes provenance fields
like `ingested_at` and `ingestion_run_id`).

### Source Identity

Unique constraint on `(source_system, source_entity, source_id)` for all canonical
entities. Source foreign keys (e.g. `customer_source_id`, `owner_source_id`) are
preserved alongside canonical FKs for unresolved-reference tracking.

---

## Canonical Schema Layer

Layer 1 uses Pydantic v2 canonical schemas (`app/schemas/canonical/`) as the
source-neutral data contract between normalization, validation, ingestion, and the API.

### Seven Canonical Schemas

| Schema | Purpose | `is_active` |
|---|---|---|
| `OrganizationCanonical` | Enterprise boundary / tenant | No |
| `EmployeeCanonical` | HR and ownership relationships | Yes |
| `CustomerCanonical` | Customer/account intelligence | Yes |
| `DealCanonical` | Sales/revenue intelligence | Yes |
| `ProjectCanonical` | Delivery/resource context | Yes |
| `SupportTicketCanonical` | Risk/support signals | No |
| `DocumentCanonical` | Future RAG/institutional memory | No |

### Key Properties

- **Pydantic v2** with `from_attributes=True` for ORM compatibility
- **Universal provenance**: `id`, `source_system`, `source_entity`, `source_id`,
  `source_updated_at`, `ingested_at`, `ingestion_run_id`, `record_hash`
- **Decimal** for monetary fields (`amount`, `budget`, `probability`)
- **Nullable canonical FKs** for unresolved cross-entity references
- **Source keys preserved** alongside canonical FKs
- **No source-specific fields** (CRM/ERP/Odoo IDs do not appear)

### Validation Boundary

Canonical schemas provide **structural** validation (types, nullability, required fields).
They do NOT perform source-specific normalization or business-rule validation.

---

## Source Schema Layer

Source schemas (`app/schemas/source/`) represent raw payloads from each source system
BEFORE normalization. They preserve source-native field names, types, and values.

```
Source System → Source Schema (B3) → Normalization (D1) → Canonical Schema (B2)
```

### Three Source Systems

| Source | Module | ID Type | Field Naming | Notes |
|---|---|---|---|---|
| CSV | `csv.py` | `str` | `customer_name`, `email_address` | All fields are strings (CSV is untyped) |
| Odoo | `odoo.py` | `int` | `partner_id`, `x_studio_segment` | Odoo-native conventions |
| REST | `rest.py` | `str` | `customerId`, `ownerId` | camelCase JSON conventions |

### Key Properties

- **No normalization**: source values are preserved exactly (no whitespace stripping,
  no status mapping, no currency conversion)
- **No canonical fields**: no `ingestion_run_id`, `ingested_at`, `record_hash`, or
  canonical UUID `id`
- **Unknown fields ignored**: `extra="ignore"` drops unmapped source fields from the
  validated object; raw payloads are preserved in `source_records.raw_payload`
- **Independent from canonical**: source schemas do NOT inherit from `CanonicalBase`

---

## Connector Base Interface

The connector abstraction (`app/connectors/`) defines a source-independent contract
that all Layer 1 connectors must satisfy.

```
CSV Connector ─────┐
Odoo Connector ────┼──> SourceConnector Protocol ──> E1 Ingestion
REST Connector ────┘
```

### SourceConnector Protocol

| Method | Returns | Purpose |
|---|---|---|
| `health_check()` | `ConnectorHealth` | Verify source reachability |
| `list_entities()` | `list[SourceEntity]` | Discover available entity types |
| `fetch_entities(entity_type, cursor, page_size)` | `Page[dict]` | Paginated source record fetch |
| `get_entity(entity_type, source_id)` | `dict` | Single record by source-native ID |
| `capabilities()` | `ConnectorCapabilities` | Declare supported features |

### Key Properties

- **Read-only**: no create/update/delete methods exist in the contract
- **Source-native payloads**: connectors return raw dicts, no normalization
- **Cursor pagination**: `Page[T]` with `next_cursor` and `has_more`
- **No database dependency**: no SQLAlchemy, no ORM, no PostgreSQL
- **No HTTP implementation**: C1 defines the contract; C2-C5 implement it

### Exception Hierarchy

`ConnectorError` → `ConfigurationError` | `AuthenticationError` |
`UnavailableError` | `RequestError` | `EntityError`

---

## CSV Connector

The CSV connector (`app/connectors/csv.py`) is the first concrete implementation of
the `SourceConnector` protocol.

```
CSV files → CsvConnector → Page[dict] → B3 Source Schemas → D1 Normalization
```

### Configuration

Entity-to-file mappings are declared in `config/connectors/csv_demo.yaml`:

```yaml
entities:
  customers:
    file: customers.csv
    id_column: customer_id
```

Mappings can be changed without modifying connector code.

### Supported Entities

All 7 canonical-domain entities: organizations, employees, customers, deals,
projects, support_tickets, documents.

### Key Properties

- **Source-native values**: all CSV values remain strings, no type conversion
- **Whitespace preserved**: `"  Acme Corp  "` stays `"  Acme Corp  "`
- **Stable source IDs**: from configured ID columns (e.g. `customer_id`)
- **Read-only**: no write operations
- **Cursor pagination**: offset-based `Page[dict]` with `next_cursor`/`has_more`
- **Unknown columns accepted**: extra CSV columns appear in the raw dict
- **No database dependency**: purely file-based
- **No normalization**: D1 handles field mapping and type conversion

### Current Limitations

- No Excel (`.xlsx`) support yet (will be added if needed)
- No incremental sync (CSV files are static snapshots)
- Re-reads entire file per `fetch_entities` call (acceptable for demo-scale data)

---

## Odoo Mock Connector

`OdooMockConnector` (`app/connectors/odoo.py`) implements the `SourceConnector`
protocol for the C3 mock-source Odoo namespace.

### Configuration

```yaml
# config/connectors/odoo.yaml
source_name: odoo_mock
source_type: mock
base_url: http://mock-source:8080
timeout: 10
```

### Supported Entities

All 7 entities: organizations, employees, customers, deals, projects,
support_tickets, documents.

### Key Properties

- **HTTP GET only**: communicates with `GET /odoo/{entity}` endpoints
- **Source-native payloads**: returns Odoo-style fields (`partner_id`,
  `x_studio_segment`, `expected_revenue`, int IDs)
- **B3 schema validation**: validates responses against Odoo source schemas
- **Cursor pagination**: offset-based via `?limit=N&offset=M`
- **Retry on transient failures**: connection errors and timeouts only
- **No normalization**: no canonical field mapping, no UUID generation
- **No persistence**: no database access
- **Docker networking**: uses `http://mock-source:8080` from API container

---

## Generic REST Connector

`RestConnector` (`app/connectors/rest.py`) implements the `SourceConnector`
protocol for configurable REST API sources via the C3 mock-source REST namespace.

### Configuration

```yaml
# config/connectors/rest.yaml
source_name: rest_mock
source_type: rest
base_url: http://mock-source:8080
timeout: 10
health_endpoint: /health

auth:
  mechanism: none  # none | api_key | bearer

entities:
  customers:
    path: /rest/customers
    description: REST customer records
  # ... all 7 entities
```

Endpoints are fully configuration-driven. No Python code changes needed to
point at a different REST API.

### Authentication

Supports `none`, `api_key`, and `bearer` mechanisms. Credentials are resolved
from environment variables at runtime, never stored in config files.

### Key Properties

- **Configuration-driven**: endpoints, auth, and health path from YAML
- **HTTP GET only**: communicates with configured REST paths
- **Source-native payloads**: returns camelCase fields (`ownerId`, `customerId`,
  `createdAt`, string IDs)
- **B3 schema validation**: validates against REST source schemas
- **Cursor pagination**: offset-based via `?limit=N&offset=M`
- **Retry on transient failures**: connection errors and timeouts only
- **No normalization**: no canonical field mapping, no UUID generation
- **No persistence**: no database access

---

## Mock Source Server

The mock-source service (`docker/mock_source.py`) reads from the shared CSV demo
dataset and serves Odoo-style and REST-style source payloads for C4/C5 connectors.

```
data/demo/*.csv (shared source of truth)
      │
      ├──────────► C2 CsvConnector (raw CSV strings)
      │
      └──────────► C3 MockSource (transforms to Odoo/REST JSON)
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
        /odoo/{entity}        /rest/{entity}
        (int IDs,              (str IDs,
         Odoo fields)           camelCase)
```

### Key Properties

- **CSV-based**: reads from configured `MOCK_SOURCE_DATA_DIR` (default: `data/demo/`)
- **GET-only**: POST/PUT/PATCH/DELETE return 405
- **Deterministic**: same CSV data always produces same JSON
- **Source-native payloads**: Odoo uses `partner_id`, `x_studio_segment`, int IDs;
  REST uses `customerId`, `ownerId`, string IDs
- **Pagination**: `?limit=N&offset=M` with `pagination.has_more` and `next_offset`
- **No database**: CSV files loaded into memory at startup
- **7 entities**: organizations, employees, customers, deals, projects,
  support_tickets, documents per source type (14 endpoints total)

### Relationship to Demo Data

Both C2 and C3 consume the same `data/demo/` CSV files. The mock-source transforms
CSV rows into source-specific representations (Odoo-style and REST-style JSON).
When E2 generates the full demo dataset, both connectors automatically pick it up.

---

## Normalization Engine (D1)

`app/normalization/` converts source-native connector payloads into validated
canonical Pydantic entities. It is pure: no database, HTTP, or connector access.

```
Connector Page[dict] → normalize() / normalize_batch() → canonical entity → D2 / E1
```

### Configuration (`config/mappings/`)

| File | Contents |
|---|---|
| `normalization.yaml` | Source-system vocabulary (`csv_demo`, `odoo_mock`, `rest_mock`), null and boolean tokens, ISO 4217 codes, canonical field kinds, enum values, decimal precision/scale |
| `<source>.yaml` | Identifier type, date/datetime formats, naive-datetime policy, decimal separators, `columns` (source field → canonical field) and explicit `derived` rules |

The loader validates the configuration against the canonical schemas and rejects
unmapped fields, duplicate targets, unknown enum values, and other inconsistencies.

### Key Rules

- **Identity**: `canonical_id` is UUID5 of `source_system:source_entity:source_id`; Odoo IDs must be positive integers.
- **Datetimes**: always timezone-aware UTC; naive values follow the source policy (CSV and Odoo: UTC, REST: rejected).
- **Decimals**: quantized to the canonical scale; values exceeding precision, scale, or range are rejected, never rounded.
- **Enums and currency**: configured canonical values; unknown labels are rejected; currencies are uppercase ISO 4217 codes.
- **`record_hash`**: SHA-256 of canonical business fields only, excluding provenance and the E1-resolved `customer_id` / `organization_id`.
- **`source_updated_at`**: extracted per record where the source provides it.
- **Errors**: every failure is a `NormalizationError` subclass with a stable `ErrorCode` and `source_system`, `entity_type`, `source_id`, `field_name`; `normalize_batch` never aborts on a malformed record.

---

## Validation and Quarantine (D2)

`app/validation/` is the quality gate that runs immediately after D1.

| Stage | Responsibility | Output |
|---|---|---|
| D1 normalization | Source-specific data → canonical form | Canonical records or `NormalizationError` |
| D2 validation | Canonical contract check → partition | Valid records **or** quarantine records, plus warnings |

```
source records → D1 normalize → D2 quality gate ─┬─→ valid canonical records → E1
                                                  └─→ quarantine records      → E1 persists
```

Entry points: `validate_source_batch` (D1 + D2 for source-native records) and
`validate_canonical_batch` (D2 for canonical records). Both return a
`QualityGateResult` in input order. Valid records are the unmodified D1 objects.

### Failure Model

| Category | Examples | Behaviour |
|---|---|---|
| **DATA failure** | Missing required field, unknown enum, invalid identifier or relationship key, invalid date/datetime/decimal/currency, wrong canonical type, non-mapping record | `QuarantineRecord`; the rest of the batch continues |
| **SYSTEM failure** | Unsupported source/entity, unexpected D1 error, configuration error, broken pipeline invariant (provenance mismatch, `record_hash`/`id` mismatch, E1 FK already set), programming bug | Exception (`QualityGateSystemError`, `CanonicalInvariantError`, or the original error); nothing is quarantined |
| **WARNING** | Duplicate source identity, missing recommended field (email) | Record stays valid; finding reported |

D2 never catches exceptions broadly: D1 error codes are classified explicitly,
and unclassified codes fail closed as system failures.

### Quarantine Record

Each `QuarantineRecord` carries `ingestion_run_id`, `source_system`, `entity_type`,
`record_index`, `stage` (`normalization` or `validation`), `source_id`, `canonical_id`,
ordered `findings` (stable `code`, `field_name`, message, safe `raw_value`), and a
safe copy of the raw record. Values under credential-like keys and bearer or
query-string credentials are redacted; long strings are truncated. Persisting
quarantine records (`ingestion_errors`, `data/quarantine/`) belongs to E1.

Policy (redaction, limits, warning rules) lives in `config/validation/quality_gate.yaml`.

---

## Demo Dataset

`scripts/seed_demo.py` generates the synthetic enterprise behind every connector. It is
deterministic: values derive from a fixed seed and the snapshot date 2026-09-01, never from
the clock, so each run writes byte-identical files and the committed CSVs are its output.

```bash
make seed                  # regenerate data/demo and the bad fixture
make seed ARGS="--check"   # exit 1 if a committed file differs; writes nothing
```

The script only writes files. Load them with `make ingest-demo`: ingestion is the only path
into PostgreSQL.

### data/demo

| Entity | Records | Contents |
|---|---|---|
| organizations | 1 | Acme Corp, the single internal company |
| employees | 24 | CEO-rooted reporting tree across seven departments; one inactive former account executive |
| customers | 50 | Enterprise / Mid-Market / SMB segments; 4 inactive; owned by active account executives |
| deals | 44 | qualification, negotiation and won; INR, USD and EUR; owned by the customer's account owner |
| projects | 22 | delivery for every won deal (in progress or planning) plus planned work for open negotiations |
| support_tickets | 80 | numbered in creation order; recent tickets are open, resolved tickets carry a resolved date |
| documents | 12 | policies, reports, contracts, a proposal, meeting notes and a runbook with full body text |

- Every reference (customer, owner, assignee, manager) resolves inside the dataset; deals,
  projects and tickets belong to active customers.
- Values use only the canonical vocabulary in `config/mappings/normalization.yaml`, so the
  dataset normalizes and validates with no quarantine and no warnings as `csv_demo`,
  `odoo_mock` and `rest_mock` payloads.
- **Churn-risk scenario** (spec Section 12): `CUST-007` raised five tickets within nine days
  (four open, four high priority) while deal `DEAL-001` is in negotiation. `CUST-004`,
  `CUST-015` and `CUST-028` have four tickets each spread over several months. Layer 1 stores
  these facts; it does not score churn.
- Figures quoted in the reports and meeting notes are checked against the records by tests.

The API and mock-source images both copy `data/demo` at build time: rebuild them
(`docker compose build`) after regenerating. The bad fixture is not copied into either image.

### Bad fixture: data/fixtures/csv_demo_bad

A separate `csv_demo` directory with the spec Section 12 quality issues beside valid records.
Its identifiers use the 9xx range, so ingesting it after the demo never modifies demo records.
Entities without issues are header-only files because the CSV health check requires every
configured file.

```bash
make ingest-demo ARGS="--data-directory data/fixtures/csv_demo_bad"
```

| Record | Issue | Outcome |
|---|---|---|
| CUST-901 | valid | inserted |
| CUST-902 | missing email | inserted; `MISSING_RECOMMENDED_FIELD` warning |
| CUST-903 | unknown status `suspended` | quarantined; `UNKNOWN_ENUM_VALUE` error |
| CUST-901 (repeat) | exact duplicate row | stored once; `DUPLICATE_SOURCE_RECORD` warning |
| DEAL-901 | valid | inserted and linked to CUST-901 |
| DEAL-902 | unknown customer `CUST-999` | inserted with `customer_id` NULL; `UNRESOLVED_REFERENCE` warning |
| DEAL-903 | malformed amount `12,50,000.00` | quarantined; `INVALID_DECIMAL` error |
| DEAL-904 | date `31/12/2026` (DD/MM/YYYY) | quarantined; `INVALID_DATE` error |

The run finishes `PARTIAL_SUCCESS` (8 fetched, 4 inserted, 1 unchanged, 3 rejected, 3 warnings);
repeating it inserts and updates nothing.

### Dataset limitations

- `employees.csv` carries `organization_id` (served as `organizationId` / `company_id` by the
  mock source), but the canonical Employee contract has no organization source key, so
  `employees.organization_id` stays NULL after ingestion (the open B1/B2 gap noted under E1).
- The canonical vocabulary is deliberately narrow (deal stages qualification, negotiation and
  won; project statuses planning and in_progress; ticket priorities medium and high; ticket
  statuses open and resolved). Richer states require a D1 configuration change.

---

## Running with Docker Compose

Start all three services (postgres, api, mock-source):

```bash
make docker-up
# or directly:
docker compose up --build -d
```

Apply migrations once the stack is healthy (the schema is never created at startup):

```bash
docker compose exec api alembic upgrade head
```

The API image contains the application, `config/` and the committed `data/demo` dataset, so every
source works inside the stack: `csv_demo` reads the files baked into the image, while `odoo_mock`
and `rest_mock` call the mock-source service. Tests, scripts, test fixtures and local caches are
not copied into the image, and nothing is mounted from the host except the PostgreSQL volume. To
load the bad fixture into the containerised database, run
`make ingest-demo ARGS="--data-directory data/fixtures/csv_demo_bad"` on the host (the default
`DATABASE_URL` points at the published PostgreSQL port).

Check service status:

```bash
docker compose ps
```

Verify the API is healthy:

```bash
curl http://localhost:8000/api/v1/health
```

Verify mock-source is healthy:

```bash
curl http://localhost:8080/health
```

Stop all services:

```bash
make docker-down
# or:
docker compose down
```

Remove all data (including PostgreSQL volume):

```bash
docker compose down -v
```

### Services and Ports

| Service | Internal Port | Host Port | Purpose |
|---|---|---|---|
| postgres | 5432 | 5432 | PostgreSQL canonical data store |
| api | 8000 | 8000 | FastAPI application |
| mock-source | 8080 | 8080 | Mock source data server |

### Startup Order

1. **postgres** starts and becomes healthy (`pg_isready`)
2. **mock-source** starts
3. **api** starts after both are available

---

## Running Locally (without Docker)

<!-- To be completed in Task I2 -->

---

## Ingestion Orchestration (E1)

`app/ingestion/` runs connector → D1 → D2 → PostgreSQL; `app/persistence/repositories/`
is its data-access layer (repositories never commit or log).

```
create run → health check → for each entity in dependency order, for each page:
    fetch → D1 + D2 quality gate → one transaction:
        source_records → FK resolution → upsert → ingestion_errors → run counts → checkpoint
→ finalize run status
```

| Concern | Behaviour |
|---|---|
| Identity | Upsert on `(source_system, source_entity, source_id)`; the canonical `id` is D1's UUID5 and never changes |
| Reconciliation | Each record is `inserted`, `updated` or `unchanged`; unchanged means the same `record_hash`, `source_updated_at` and resolved FKs. Duplicates in a batch: the last occurrence wins. No deletes, no cross-source merging |
| Foreign keys | `customer_id` is resolved from `customer_source_id` against customers of the same source; unresolved → NULL + `UNRESOLVED_REFERENCE` warning. `employees.organization_id` stays NULL: the canonical contract carries no organization source key (open B1/B2 gap) |
| Transactions | One transaction per fetched page, advisory-locked per source entity; a failed batch rolls back completely |
| Quarantine | One `ingestion_errors` ERROR row per rejected record, with D2's redacted payload in `detail`; D2 warnings become WARNING rows |
| Raw capture | Append-only `source_records` rows per run for every record with a known source identity (unmodified payload; never logged) |
| Status | `FAILED` (health check failed, or failures with nothing committed) · `PARTIAL_SUCCESS` (entity or batch failure, or rejected records) · `NOOP` (nothing inserted or updated) · `SUCCESS` |
| Failures | Connector authentication/configuration errors stop the run; other connector errors fail one entity; `IntegrityError`/`DataError` fail one batch (`BATCH_FAILED`, SQLSTATE only); anything else marks the run `FAILED` and propagates |
| Checkpoint | `ingestion_cursors` advances only when an entity's final page commits. Only `full` mode exists: no connector supports incremental sync |
| Counts | `fetched = inserted + updated + unchanged + rejected + failed`; records of a failed batch are included in `records_fetched` and described by its `BATCH_FAILED` row |

Logs and summaries carry identifiers, counts and exception class names only.

---

## Observability (G1)

### Structured logs

The API (at startup) and `make ingest-demo` configure the `app` logger from two settings. Logs go
to stderr, so the ingest command's JSON summary on stdout stays machine-readable.

| Setting | Values | Default |
|---|---|---|
| `APP_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (case-insensitive) | `INFO` |
| `LOG_FORMAT` | `json` (one JSON object per line) or `text` | `json` |

Invalid values stop API startup and make `ingest-demo` exit with status `2`.

```text
# LOG_FORMAT=json
{"timestamp":"2026-09-15T09:30:01.412Z","level":"INFO","logger":"app.ingestion.orchestrator","event":"run_finished","run_id":"5f0c...","status":"SUCCESS","fetched":94,"inserted":94,"updated":0,"unchanged":0,"rejected":0,"failed":0,"warnings":0,"duration_seconds":0.4123}
# LOG_FORMAT=text
2026-09-15T09:30:01.412Z INFO app.ingestion.orchestrator run_finished run_id=5f0c... status=SUCCESS ... duration_seconds=0.4123
```

Every JSON line has `timestamp` (UTC, milliseconds), `level`, `logger` and `event`, followed by
the event's fields as typed JSON values. Text lines escape carriage returns and newlines.

| Event | Level | Logger | Fields |
|---|---|---|---|
| `run_started` | INFO | `app.ingestion.orchestrator` | `run_id`, `source_system`, `entities` |
| `connector_health_check_failed` | WARNING | orchestrator | `run_id`, `source_system`, `failure` |
| `batch_fetched` | INFO | orchestrator | `run_id`, `entity`, `page`, `records`, `has_more` |
| `record_normalized` | DEBUG | orchestrator | `run_id`, `entity`, `page`, `record_index`, `source_id` |
| `record_rejected` | WARNING | orchestrator | `run_id`, `entity`, `page`, `record_index`, `source_id`, `stage`, `codes` |
| `batch_committed` | INFO | orchestrator | `run_id`, `entity`, `page`, `fetched`, `inserted`, `updated`, `unchanged`, `rejected`, `warnings` |
| `batch_failed` | WARNING | orchestrator | `run_id`, `entity`, `page`, `records`, `database_error`, `sqlstate` |
| `entity_failed` | WARNING | orchestrator | `run_id`, `entity`, `page`, `failure`, `run_stopped` |
| `run_finished` | INFO | orchestrator | `run_id`, `status`, run counts, `duration_seconds` |
| `run_failed` | ERROR | orchestrator | `run_id`, `failure` |
| `retry_scheduled` | WARNING | `app.connectors.rest`, `app.connectors.odoo` | `source`, `attempt`, `max_attempts`, `delay_seconds`, `reason` |
| `connector_health_check` | INFO | `app.api.v1.sources` | `source`, `status`, `error_type` |
| `ingestion_run_requested` / `ingestion_run_finished` | INFO | `app.api.v1.ingestion` | `request_id`, `source`, `entities` / `request_id`, `run_id`, `status` |
| `readiness_check_failed`, `source_misconfigured`, `request_failed` | WARNING / ERROR | API | dependency or source, exception class; `request_failed` adds `request_id`, `method`, `path` |

- `record_normalized` is per accepted record and only built at `DEBUG`. `record_rejected`'s
  `codes` lists the distinct finding codes in finding order; `stage` is `normalization` or
  `validation`.
- `retry_scheduled` is logged just before each backoff sleep; `reason` is `http_429`, `http_502`,
  `http_503`, `http_504` or the httpx exception class.
- **Never logged**: source values, raw records, rejected values, connector messages, URLs,
  headers, credentials, exception messages or tracebacks (only the exception class).

### In-process counters

`GET /api/v1/metrics/ingestion` also returns `process`: counters for the runs this API process
executed since it started (see [Ingestion metrics](#ingestion-metrics)).

---

## Ingestion Commands

```bash
make ingest-demo
```

Equivalent to `python scripts/ingest_demo.py`, which prints the run summary as JSON.
Running it again is a `NOOP`. Options (pass through `ARGS="..."` with make):

| Option | Purpose |
|---|---|
| `--source {csv_demo,odoo_mock,rest_mock}` | Connector from `config/connectors/` (default `csv_demo`) |
| `--entities customers deals ...` | Limit the run; parents are still processed first |
| `--page-size N` | Records per batch transaction (default 100) |
| `--base-url URL` | HTTP sources only, e.g. `http://localhost:8080` outside Docker |
| `--data-directory DIR` | `csv_demo` only |

Exit status: `0` SUCCESS / PARTIAL_SUCCESS / NOOP, `1` FAILED, `2` invalid request, connector
configuration or logging settings (no run created). The database comes from `DATABASE_URL`. Log
events go to stderr in the `LOG_FORMAT` format at `APP_LOG_LEVEL`.

---

## API Usage Examples

The API is versioned under `/api/v1` (synchronous FastAPI routes). Interactive documentation is
served at `/docs` and the schema at `/openapi.json`. The examples assume the API on
`localhost:8000`.

| Method | Path | Purpose | Success |
|---|---|---|---|
| GET | `/api/v1/health` | Liveness and readiness (PostgreSQL reachable) | `200` healthy · `503` unhealthy |
| GET | `/api/v1/sources` | Configured sources and their capabilities | `200` |
| GET | `/api/v1/sources/{source}/health` | Run one connector health check | `200` |
| POST | `/api/v1/ingestion/runs` | Run one ingestion to completion | `201` + `Location` |
| GET | `/api/v1/ingestion/runs` | List runs (`source_system`, `status`, `limit`, `offset`) | `200` |
| GET | `/api/v1/ingestion/runs/{run_id}` | Run detail and counts | `200` |
| GET | `/api/v1/ingestion/runs/{run_id}/errors` | Structured errors (`severity`, `limit`, `offset`) | `200` |
| GET | `/api/v1/entities/{entity_type}` | Canonical records (`source_system`, `limit`, `offset`) | `200` |
| GET | `/api/v1/entities/{entity_type}/{id}` | One canonical record by canonical id | `200` |
| GET | `/api/v1/metrics/ingestion` | Operational ingestion metrics, in total and per source | `200` |

`entity_type` is one of `organizations`, `employees`, `customers`, `deals`, `projects`,
`support_tickets` or `documents`.

### Health and sources

```bash
curl http://localhost:8000/api/v1/health
# {"status": "healthy", "service": "ai-ceo-layer1", "version": "0.1.0", "checks": {"database": "ok"}}

curl http://localhost:8000/api/v1/sources
# {"sources": [{"source": "csv_demo", "source_type": "csv",
#   "capabilities": {"supported_entity_types": ["customers", ...], "supports_incremental": false,
#                    "supports_health_check": true, "read_only": true}}, ...]}

curl http://localhost:8000/api/v1/sources/odoo_mock/health
# {"source": "odoo_mock", "status": "healthy", "latency_ms": 3.1, "error_type": null,
#  "checked_at": "2026-09-14T12:00:00Z"}
```

Application health and connector health are separate: `/health` returns `503` only when
PostgreSQL is unreachable. A connector check always returns `200` with `status` `healthy`,
`unhealthy` or `unsupported`; `error_type` is the connector exception class when the check
raised. Connector messages, URLs and data paths are never returned.

### Starting a run

```bash
curl -i -X POST http://localhost:8000/api/v1/ingestion/runs \
  -H 'Content-Type: application/json' \
  -d '{"source": "csv_demo", "entities": ["customers", "deals"], "mode": "full", "dry_run": false}'
# HTTP/1.1 201 Created
# location: /api/v1/ingestion/runs/5f0c...
# x-request-id: 2b7e...
# {"run_id": "5f0c...", "source_system": "csv_demo", "status": "SUCCESS",
#  "records_fetched": 94, "records_raw_persisted": 94, "records_inserted": 94, ...,
#  "batches_committed": 2, "entities": [{"entity_type": "customers", "status": "completed", ...}]}
```

| Field | Rule |
|---|---|
| `source` | Required; one of the configured sources |
| `entities` | Optional; omitted means every entity the source provides; parents always run first |
| `mode` | `full` only |
| `dry_run` | Optional, default `false`; `true` is rejected with `422 UNSUPPORTED_OPTION` |
| `page_size` | Optional integer 1–10000 (default 100): records per batch transaction |

The run executes before the response is sent, and the response is the completed run whatever
its status: a run whose source health check fails is `201` with status `FAILED`. Repeating a
request is idempotent (`NOOP`). Unknown fields are rejected, so connection details such as base
URLs or data directories cannot be supplied through the API.

### Runs and errors

```bash
curl 'http://localhost:8000/api/v1/ingestion/runs?status=PARTIAL_SUCCESS&limit=10'
curl http://localhost:8000/api/v1/ingestion/runs/5f0c...
curl 'http://localhost:8000/api/v1/ingestion/runs/5f0c.../errors?severity=ERROR'
# {"items": [{"id": "...", "severity": "ERROR", "code": "UNKNOWN_ENUM_VALUE",
#   "message": "value is not in the canonical vocabulary for this field",
#   "source_system": "csv_demo", "source_entity": "customers", "source_id": "CUST-903",
#   "created_at": "...", "findings": [{"code": "UNKNOWN_ENUM_VALUE", "field_name": "status",
#   "severity": "ERROR", "message": "value is not in the canonical vocabulary for this field"}]}],
#  "total": 3, "limit": 50, "offset": 0}
```

- **Pagination**: `limit` 1–500 (default 50) and `offset` ≥ 0; every page reports `total`,
  `limit` and `offset`. Runs are ordered newest first (`started_at`, then `id`); errors by
  `created_at`, then `id`. Each request reads one read-only snapshot.
- **Counts**: `records_fetched = records_inserted + records_updated + records_unchanged +
  records_rejected + records_failed`. `records_raw_persisted` counts captured raw records and
  `batches_failed` counts rolled-back batches. `batches_committed` and per-entity results are
  only in the `POST` response.
- **Safe error messages**: stored D1/D2 diagnostics quote the rejected source value
  (e.g. `unknown value 'suspended'`) and keep a redacted copy of the raw record. The API never
  returns them. Errors raised by E1 itself (`UNRESOLVED_REFERENCE`, `CONNECTOR_UNHEALTHY`,
  `CONNECTOR_FAILED`, `BATCH_FAILED`) keep their stored message, which names entities, fields,
  counts and exception classes only. Every D1/D2 code maps to a fixed description, and any
  other code reads `record failed data quality checks`. `raw_record`, `raw_value`, source keys and
  stored D1/D2 messages stay in `ingestion_errors` for debugging.

### Canonical entities

These are the stable Layer 2 handoff contract: records come from the canonical tables, never
from a source system, and consumers do not need to know which connector produced them.

```bash
curl 'http://localhost:8000/api/v1/entities/customers?source_system=csv_demo&limit=2'
# {"items": [{"id": "0b3f...", "source_system": "csv_demo", "source_entity": "customers",
#   "source_id": "CUST-001", "source_updated_at": null, "ingested_at": "...",
#   "ingestion_run_id": "5f0c...", "record_hash": "9a1e...", "name": "Falconridge Foods",
#   "email": "contact@falconridge-foods.example", "segment": "...", "industry": "...",
#   "status": "...", "owner_source_id": "EMP-010", "created_at": "...", "is_active": true}, ...],
#  "total": 50, "limit": 2, "offset": 0}

curl http://localhost:8000/api/v1/entities/deals/0b3f...
# {"id": "...", "source_id": "DEAL-001", "amount": "5361.44", "currency": "USD",
#  "probability": "90.00", "customer_source_id": "CUST-007", "customer_id": "...", ...}
```

- **Records**: every canonical column is returned: the business fields and the provenance fields
  `id`, `source_system`, `source_entity`, `source_id`, `source_updated_at`, `ingested_at`,
  `ingestion_run_id` and `record_hash`. Documents include the full `body_text`. Unresolved
  references keep their source key with a `null` canonical id (e.g. `customer_id`).
- **Identity**: `{id}` is the canonical UUID. An id that belongs to another entity type is
  `404 ENTITY_NOT_FOUND`, and an unknown entity type is `404 NOT_FOUND`.
- **Pagination and order**: `limit` 1–500 (default 50) and `offset` ≥ 0, with `total`, `limit`
  and `offset` on every page. Records are ordered by source identity (`source_system`,
  `source_entity`, `source_id`), which is unique and unchanged by re-ingestion. Each request reads
  one read-only snapshot.
- **Decimals**: `amount`, `probability` and `budget` are JSON strings (e.g. `"5361.44"`), never
  floats.
- **No raw payloads**: rejected records never reach the canonical tables, and raw source payloads
  in `source_records` are not served.

### Ingestion metrics

```bash
curl http://localhost:8000/api/v1/metrics/ingestion
# {"totals": {"runs_total": 6, "runs_by_status": {"RUNNING": 0, "SUCCESS": 3, "PARTIAL_SUCCESS": 0,
#             "FAILED": 0, "NOOP": 3},
#             "records_fetched_total": 1398, "records_raw_persisted_total": 1398, ...,
#             "errors_by_severity": {"ERROR": 0, "WARNING": 0, "INFO": 0},
#             "connector_request_failures_total": 0, "validation_errors_total": 0,
#             "ingestion_duration_seconds_total": ...,
#             "canonical_records": {"organizations": 3, "employees": ..., ...}},
#  "sources": [{"source_system": "csv_demo", "runs_total": 2, ...,
#               "last_run": {"run_id": "...", "status": "NOOP", "started_at": "...",
#                            "finished_at": "..."},
#               "last_successful_run": {...}}, ...],
#  "process": {"started_at": "2026-09-15T09:00:00.184322Z", "runs_total": 2,
#              "runs_by_status": {"RUNNING": 0, "SUCCESS": 1, "PARTIAL_SUCCESS": 0, "FAILED": 0,
#                                 "NOOP": 1},
#              "records_fetched_total": 466, "records_inserted_total": 233, ...,
#              "connector_request_failures_total": 0, "validation_errors_total": 0,
#              "ingestion_duration_seconds": {"count": 2, "sum": 0.8231}}}
```

`totals` and `sources` are derived from the database (`ingestion_runs`, `ingestion_errors`,
`source_records` and the canonical tables) in one read-only snapshot, so they survive restarts and
agree across API processes. `process` is counted in memory by the API process that answers.

| Metric | Definition |
|---|---|
| `runs_total`, `runs_by_status` | Runs, and runs per status (all five statuses always listed) |
| `records_fetched_total` … `records_rejected_total`, `warnings_total` | Sums of the run report counts |
| `records_raw_persisted_total` | Raw `source_records` rows captured by the runs |
| `records_failed_total` | `fetched − (inserted + updated + unchanged + rejected)`: records of failed batches |
| `batches_failed_total` | `BATCH_FAILED` errors |
| `errors_by_severity` | `ingestion_errors` rows per severity (`ERROR`, `WARNING`, `INFO`) |
| `connector_request_failures_total` | `CONNECTOR_UNHEALTHY` and `CONNECTOR_FAILED` errors |
| `validation_errors_total` | `ERROR` findings other than `CONNECTOR_*` and `BATCH_FAILED`: the D1/D2 rejections |
| `ingestion_duration_seconds_total` | Sum of `finished_at − started_at` over finished runs |
| `canonical_records` | Canonical records per entity type |
| `last_run`, `last_successful_run` | Per source: the newest run, and the newest `SUCCESS`, `PARTIAL_SUCCESS` or `NOOP` run |

- **Sources**: `totals` covers everything; `sources` lists every configured source (zeros when it
  has no data) and any other source system with runs or canonical records, sorted by name.
- **Attribution**: runs, their errors and their raw records count toward the run's
  `source_system`. A `RUNNING` run contributes the counts it has committed so far but no duration.
- **Never exposed**: error messages, run error summaries, raw records and source values.

`process` holds in-process counters (spec Section 16 names) for runs started through
`POST /api/v1/ingestion/runs` in this API process:

| Counter | Definition |
|---|---|
| `started_at` | When this application process started; every counter begins at zero then |
| `runs_total`, `runs_by_status` | Runs started here; `RUNNING` counts runs still in progress |
| `records_fetched_total` … `records_rejected_total` | Counts of committed batches; records of a failed batch count as fetched |
| `connector_request_failures_total` | Failed connector health checks and failed page fetches |
| `validation_errors_total` | Records rejected by the D1/D2 quality gate |
| `ingestion_duration_seconds` | `count` of finished runs and `sum` of their `finished_at − started_at` |

The counters use the same definitions as the database-derived metrics and are updated when E1
commits, so for a process that performed every ingestion against an empty database they agree
with `totals`. They reset when the process restarts, are not shared between API workers, and do
not include runs of `make ingest-demo` or other processes; the database-derived metrics remain the
durable record.

### Error responses

Every error has one shape, and the same `request_id` is sent in the `X-Request-ID` header (a
client-supplied `X-Request-ID` of 1–64 characters `[A-Za-z0-9._-]` is reused):

```json
{"error": {"code": "SOURCE_NOT_FOUND", "message": "source is not configured",
           "details": {"available_sources": ["csv_demo", "odoo_mock", "rest_mock"]},
           "request_id": "2b7e..."}}
```

| Code | Status | Meaning |
|---|---|---|
| `INVALID_REQUEST` | 422 | Parameter or body validation failed (`details` lists location, message and type) |
| `NOT_FOUND` / `METHOD_NOT_ALLOWED` | 404 / 405 | Unknown route or method |
| `SOURCE_NOT_FOUND` | 404 (path) · 422 (`POST` body) | The source is not configured |
| `SOURCE_MISCONFIGURED` | 500 | The source's connector configuration is invalid |
| `RUN_NOT_FOUND` | 404 | The ingestion run does not exist |
| `UNSUPPORTED_OPTION` | 422 | `dry_run: true` was requested |
| `INVALID_INGESTION_REQUEST` | 422 | E1 rejected the request for this source (e.g. entities it does not provide) |
| `ENTITY_NOT_FOUND` | 404 | No record of that entity type has the id (`details` names the `entity_type`) |
| `INTERNAL_ERROR` | 500 | Unexpected failure; the message is generic and details are never exposed |

Rejected requests (`422`, `SOURCE_MISCONFIGURED`) create no run. A system failure during a run
returns `500 INTERNAL_ERROR` after E1 has marked the run `FAILED`.

### API limitations

- **No authentication or authorization**: Layer 1 is a prototype, and anyone who can reach the
  API can start runs. Deploy it only on a trusted network.
- **Synchronous runs**: `POST /ingestion/runs` holds the request open for the whole run. There is
  no server-side timeout, and a client disconnect does not cancel the run.
- **No dry run and full mode only**: E1 has neither dry-run semantics nor incremental sync.
- **Counts**: the run report has no `normalized` count, because E1 does not record one.
  Per-entity results are not persisted, so only the `POST` response includes them.
- **Error order within a batch**: errors written in one batch share `created_at` and are ordered
  by `id`, not by record order.
- **Correlation on system failure**: a `500` during a run carries the request ID but not the run
  ID (E1 does not expose it). The run is listed as `FAILED`, and the request ID is logged beside
  the run ID only for runs that finish. A run interrupted by a process crash stays `RUNNING`.
- **Source configuration**: sources come from `config/connectors/*.yaml`, and each connector is
  built once per process, so configuration changes need a restart. The `connector_configs` table
  is not used.
- **Docker images bake in the dataset**: the API and mock-source images copy `data/demo` at build
  time, so regenerated data needs `docker compose build`.
- **Logs and counters are per process**: structured logs go to the process's stderr (no log
  shipping), `process` counters reset on restart and cover one API worker only, and there is no
  Prometheus exposition. `retry_scheduled` carries the source but not the run ID (connectors do
  not know the run); it appears between the run's `batch_fetched` events in the same process.
- **Entity queries**: the only filter is `source_system`; there are no field filters, search or
  alternative sort orders. Pagination is by offset, and each page is its own snapshot, so an
  ingestion that inserts records between two page requests can shift later pages.

---

## Test Commands

<!-- To be completed in Task H1–H5 and I2 -->

---

## Layer 1 Acceptance Checklist

<!-- To be completed in Task I1 -->

---

## Troubleshooting

<!-- To be completed in Task I2 -->

---

## Known Limitations

This is a prototype. See the Layer 1 Master Build Prompt (CONTEXT/Layer1_Prompt/) for the full scope definition.

---

## Project Source Documents

- `CONTEXT/INTRODUCTION/AI_CEO_Project_Proposal.pdf`
- `CONTEXT/Layer1_Prompt/AI_CEO_Layer_1_Master_Build_Prompt.pdf`
- `CONTEXT/AI_CEO_PROJECT_CONTEXT.md` — confirmed design decisions and task map
