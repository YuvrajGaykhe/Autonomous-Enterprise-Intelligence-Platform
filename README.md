# AI CEO — Layer 1: Connector and Ingestion Subsystem

> **Group 11 | Final Year Project | B.E. Computer Engineering, SPPU**
> Layer 1 of the AI CEO platform — the Connector Layer.

---

## Architecture

Layer 1 is the Connector Layer. It reads enterprise sources **read-only**, captures each raw
payload with its provenance, normalizes and validates it deterministically, upserts canonical
records into PostgreSQL, and serves them over a versioned HTTP API to later AI CEO layers. No
LLM is involved: every transformation is configuration-driven code.

```
       sources (read-only)              Layer 1 pipeline                        consumers
  ┌──────────────────────────┐   ┌──────────────────────────────────┐   ┌────────────────────┐
  │ csv_demo   data/demo/*.csv│──▶│ connector    GET / open() only   │   │                    │
  │ odoo_mock  mock-source    │──▶│      ▼                           │   │  FastAPI /api/v1   │
  │ rest_mock  mock-source    │──▶│ raw capture  source_records      │   │  health · sources  │
  └──────────────────────────┘   │      ▼                           │   │  ingestion · runs  │
                                  │ normalize    D1 mapping+coercion │   │  entities · metrics│
                                  │      ▼       UUID5 id, hash      │   │         ▲          │
                                  │ validate     D2 quality gate     │   └─────────┼──────────┘
                                  │      ▼       accept | quarantine │             │
                                  │ persist      upsert on source    │─────────────┘
                                  │              identity, run stats │   PostgreSQL
                                  └──────────────────────────────────┘   7 canonical + 5 operational
```

Every stage is a separate module, so a source, a mapping or a rule can change without touching
the others:

| Stage | Module | Contract |
|---|---|---|
| Connect | `app/connectors/` | One `SourceConnector` protocol; `capabilities()`, `list_entities()`, `get_entity()`, `health_check()`. No write method exists |
| Capture | `app/persistence/repositories/raw.py` | Append-only `source_records`: the unmodified payload plus run and source identity |
| Normalize | `app/normalization/` | `config/mappings/*.yaml` drive field mapping, type coercion, the UUID5 canonical id and the record hash |
| Validate | `app/validation/` | Pydantic canonical schemas plus `config/validation/quality_gate.yaml`: each record is accepted or quarantined with structured findings |
| Persist | `app/persistence/` | Upsert on `(source_system, source_entity, source_id)`; `ingestion_runs`, `ingestion_errors`, `ingestion_cursors` |
| Orchestrate | `app/ingestion/orchestrator.py` | One transaction per fetched page; run status, counts and checkpoints (see [Ingestion Orchestration](#ingestion-orchestration-e1)) |
| Serve | `app/api/v1/` | Read-only routes plus the one write, `POST /ingestion/runs` (see [API Usage Examples](#api-usage-examples)) |
| Observe | `app/core/logging.py`, `app/observability/` | Structured events keyed by run id, in-process counters, `GET /metrics/ingestion` |
| Guard | `app/core/security.py` | The read-only same-origin HTTP client and the import-file checks every connector goes through |

**Repository layout**

```
app/           main.py, api/v1, connectors, schemas (source + canonical),
               normalization, validation, ingestion, persistence (models +
               repositories), observability, core (config, logging, security)
config/        connectors/  one YAML per source
               mappings/    per-source field maps + the shared normalization vocabulary
               validation/  quality_gate.yaml
data/          demo/        the committed deterministic dataset
               fixtures/    csv_demo_bad, the deliberately malformed fixture
               raw/, quarantine/  reserved (empty)
docker/        mock_source.py and its Dockerfile — the C3 deterministic source server
migrations/    Alembic environment and the committed revisions
scripts/       seed_demo.py, ingest_demo.py, secret_scan.py, verify_layer1.py
tests/         unit/, contract/, integration/, e2e/ and the shared PostgreSQL harness
```

Three services run the system: `postgres`, `api` and `mock-source`
(see [Running with Docker Compose](#running-with-docker-compose)).

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

Options (pass through `ARGS="..."` with make):

| Option | Purpose |
|---|---|
| `--check` | Report stale files and exit `1` instead of writing |
| `--demo-dir DIR` | Where the demo dataset is written (default `data/demo`) |
| `--bad-fixture-dir DIR` | Where the malformed fixture is written (default `data/fixtures/csv_demo_bad`) |

Exit status: `0` files written or already up to date, `1` `--check` found stale files.

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

Everything except PostgreSQL runs directly from a virtualenv. Every `make` target that runs
Python runs it as `.venv/bin/...`, so `make install` comes first.

```bash
make install                         # python3 -m venv .venv + pip install -e ".[dev]"
docker compose up -d postgres        # or point .env at any reachable PostgreSQL 16
cp .env.example .env                 # defaults already match the compose postgres
make migrate                         # empty database -> current schema
make ingest-demo                     # load data/demo through the csv_demo connector
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The API is then on `http://localhost:8000` with its docs at `/docs`. The demo dataset is
committed, so `make seed` is only needed after changing the generator.

The `odoo_mock` and `rest_mock` sources read the C3 mock source, whose committed `base_url` is
`http://mock-source:8080` — a name that only resolves inside the compose network. From the host,
start the container and override the URL:

```bash
docker compose up -d mock-source
make ingest-demo ARGS="--source rest_mock --base-url http://localhost:8080"
```

The API never accepts a base URL or a data directory from a request, so an API process outside
Docker needs the committed configuration to be reachable as written.

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

## Security (G2)

Layer 1 enforces the spec Section 14 constraints in code, and its tests prove that secrets are
never returned or logged (spec Section 15).

### Source access

Every connector uses the checks in `app/core/security.py`:

| Check | Rule |
|---|---|
| `base_url` (Odoo mock, REST) | `http` or `https`; a host; a port from 1 to 65535 if one is given. No embedded credentials, query string, fragment, whitespace or control characters |
| REST `health_endpoint` and entity `path` | one leading `/`. No `//`, backslash, `..` segment, query or fragment, so a path can never name another host |
| `timeout` | finite seconds, greater than 0 and at most 300; booleans are rejected |
| HTTP client | GET only, only to `base_url`'s scheme, host and port, and redirects are never followed. Any other request is refused before it is sent |
| CSV entity `file` | a plain file name ending in `.csv` (any case), with no directory components or control characters |
| CSV reads | the file must resolve inside the data directory (symlinks included), be a regular file, and be no larger than `max_file_bytes`. The limit defaults to 52,428,800 bytes (50 MiB) and can be set in the connector YAML |

Invalid configuration raises `ConnectorConfigurationError`, with messages such as
`Invalid base_url: <rule>`, `Invalid timeout: <rule>`, `Entity '<type>' has an invalid path: <rule>`,
`Entity '<type>' has an invalid file: <rule>` and `Invalid max_file_bytes: <rule>`. Messages name
the broken rule, never the value, because a URL can embed credentials. `ingest_demo --base-url` is
validated the same way. A refused CSV read raises `ConnectorRequestError`
(`Source file for entity '<type>' was refused: <rule>`), and E1 records it as a connector failure.

### Secrets

- Credentials come only from environment variables: `.env` is gitignored, and `.env.example`
  holds placeholders only. REST authentication names the variable in `auth.env_var`, never its
  value.
- `Settings` hides `postgres_password` and `database_url` from `repr()`. No engine echoes SQL, and
  the API engine and `app.core.database.get_engine` also hide bound parameters from database errors.
- These are never returned by the API, logged, or printed by `ingest-demo`: credentials, connector
  exception messages, upstream response bodies, URLs, raw records, raw values and exception text.
  API errors use fixed messages, and logs carry only exception class names.

### Secret scan

```bash
make secret-scan
```

This runs `scripts/secret_scan.py` over every git-tracked text file. Each finding is printed as
`path:line: rule [fingerprint]`. The fingerprint is the first 12 hex characters of the value's
SHA-256; the value itself is never printed. Exit status is `0` when the scan is clean, `1` when it
has findings, and `2` when it could not run.

| Rules | What they find |
|---|---|
| Provider | private keys, AWS access key IDs, GitHub, Slack, `sk-` style and Google API keys, JWTs |
| Generic | credentials in URLs; bearer tokens; quoted assignments to password, secret, token or key names; unquoted assignments in `.env*`, `.ini`, `.cfg`, `.conf`, `.properties`, `.sh` and YAML files |
| Hygiene | no tracked `.env` file (only `.env.example`); `.gitignore` ignores `.env`; every secret-named `.env.example` value is a placeholder |

Generic rules skip visible placeholders and templates (such as `changeme`, `synthetic`, `example`,
`${...}` and `{...}`) and values shorter than 8 characters. Six synthetic D2/C5 test fixtures are
pinned in `ALLOWED_FINDINGS` by path, rule and fingerprint, each with a reason.

### Security tests

| Test file | Covers |
|---|---|
| `tests/unit/test_g2_outbound_safety.py` | URL, path and timeout rules; the GET-only, same-origin client; connector configuration; `--base-url` |
| `tests/unit/test_g2_import_safety.py` | CSV file names, directory containment, symlinks and size limits |
| `tests/unit/test_g2_secret_hygiene.py` | scanner rules and command; the clean repository; `Settings` repr; engine flags |
| `tests/unit/test_g2_security_boundary.py` | static checks: no eval, exec, pickle or unsafe YAML loading; HTTP clients built only in `app.core.security`; connectors only GET; logging only through `log_event`, with no credential-named fields or exception text; no textual SQL; no credential-shaped API fields |
| `tests/integration/test_g2_secret_canary.py` | canary secrets injected through the environment, upstream responses, CSV payloads, request bodies, an unreachable `DATABASE_URL` and exceptions never appear in any API response, the OpenAPI document, JSON or text logs, or `ingest-demo` output |

### Security limitations

- **No authentication**: see [API limitations](#api-limitations).
- **No host allowlist**: URL validation is structural, so any well-formed host in committed
  configuration or `--base-url` is accepted.
- **CSV files are checked when read**: health checks and entity discovery only check that the
  configured files exist.
- **The secret scan is heuristic**: it covers tracked text files only, not git history or binary
  documents (PDF, PPTX). Generic rules miss values shorter than 8 characters or marked as
  placeholders. They also report a long non-placeholder value assigned to a secret-named variable
  even when it is not a secret; rename such variables rather than widening the markers.
- **Canonical business data is returned as ingested**: if a source stores a credential inside a
  business field (for example document `body_text`), the entity API returns it.
- **`ingest-demo` system failures** still end with a Python traceback. The canary test verifies
  that the database error text does not contain the password.

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
| `HTTP_ERROR` | any other | The fallback code for any other HTTP failure the framework raises |
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

Run everything:

```bash
make test
```

`make test` runs `pytest` over `tests/`, which is 4139 tests in four layers
(spec Section 15). The layers differ in what they need, so select them by path:

| Layer | Command | Tests | Needs |
|---|---|---|---|
| Unit | `pytest tests/unit` | 3381 | nothing |
| Connector contract | `pytest tests/contract` | 185 | nothing |
| Database integration | `pytest tests/integration` | 493 | PostgreSQL |
| End-to-end | `pytest tests/e2e` | 80 | PostgreSQL |

The unit and contract layers run with no database at all: the contract suite
starts the mock-source in-process and reads the committed CSVs directly, so
`pytest tests/unit tests/contract` passes even with `DATABASE_URL` pointing
nowhere. The integration and end-to-end layers need a reachable PostgreSQL
(`make docker-up` is enough); they recreate `<database>_test` once per session,
migrate it from empty with the committed Alembic migrations, and truncate every
table between tests. Never run two such sessions concurrently — they share that
database.

The `contract`, `integration` and `e2e` pytest markers select the same sets as
the corresponding paths. The `unit` marker is applied only to a few modules, so
prefer the path for that layer.

### What each layer covers

| Layer | Coverage |
|---|---|
| Unit | Field mapping, type coercion, identifier generation, record hashing, validation rules, configuration loading, pagination helpers, and the fail-loud guards behind each |
| Connector contract | One suite run against all three real connectors over the same demo dataset: shared interface, agreement between `capabilities()` and `list_entities()`, deterministic pagination, `get_entity` round-trips, a shared failure vocabulary, and read-only behaviour proved by method names, static inspection and the live mock-source's request log |
| Database integration | Migrations (single head, empty database to head, model/schema parity, reversible and repeatable), constraints (source identity uniqueness, provenance NOT NULL, foreign keys and their delete rules), upsert by source identity, and run tracking |
| End-to-end | Demo source to ingestion to PostgreSQL to API query, entirely over HTTP; repeated ingestion without duplicate canonical identities; failure recovery for malformed rows, connector and network failures, database failures and partial batches; and the acceptance scenario of [`make verify-layer1`](#layer-1-acceptance-checklist) |

### Related checks

```bash
make lint           # ruff over app/ tests/, mypy over app/
make secret-scan    # scan tracked files for committed secrets
make verify-layer1  # the acceptance scenario against a running stack
```

`make lint` exits non-zero: it reports the project's known lint and type debt rather than
suppressing it (see [Known Limitations](#known-limitations)). `make secret-scan` and
`make verify-layer1` exit `0` when they pass.

Line coverage of `app/` is 100%:

```bash
pytest --cov=app --cov-report=term-missing
```

---

## Layer 1 Acceptance Checklist

The full acceptance scenario of the build prompt (Section 20, steps A–O) is a command:

```bash
make docker-up          # the scenario needs a running stack
make verify-layer1
```

`make verify-layer1` runs `python scripts/verify_layer1.py`, which drives the running stack over
HTTP the way a reviewer would: it reads readiness, source health, canonical records, runs and
errors through the published API, checks the committed CSVs against the deterministic generator,
and starts its ingestion runs with `POST /ingestion/runs`. Only the malformed fixture (steps K–L)
goes in through `run_ingestion()`, because the API deliberately refuses a data directory from a
request; it is then read back through the API, which also proves the command and the API are on
one database. Options (pass through `ARGS="..."` with make):

| Option | Purpose |
|---|---|
| `--base-url URL` | The running API (default `http://localhost:8000`) |
| `--timeout SECONDS` | Per-request timeout (default 180) |
| `--page-size N` | Ingestion page size (default 100) |
| `--with-tests` | Also run the whole test suite (step N) |

Exit status: `0` every executed check passed, `1` a check failed, `2` the scenario could not run
(unreachable API, invalid arguments or logging settings). The report goes to stdout; the log
events of the malformed-fixture run go to stderr in the usual `LOG_FORMAT`. Run it on the host,
not inside the API container: the container image deliberately excludes `data/fixtures/`.

The command writes only through ingestion, so repeating it is safe — a second run is a `NOOP`.
On a clean database it reports:

```
verify-layer1: A-C  stack_ready       PASS      ai-ceo-layer1 0.1.0 ready, database ok, all 7 canonical tables queryable, database empty
verify-layer1: D    demo_dataset      PASS      14 committed CSV files regenerate byte-identically; demo dataset holds customers 50, deals 44, documents 12, employees 24, organizations 1, projects 22, support_tickets 80
verify-layer1: E-F  ingestion         PASS      run f245b8f6 SUCCESS: fetched 220 = 220 inserted + 0 updated + 0 unchanged + 0 rejected + 0 failed, 220 raw records persisted over 5 entity types
verify-layer1: G-H  api_query         PASS      full provenance and consistent pagination for customers 50, deals 44, support_tickets 80
verify-layer1: I-J  idempotency       PASS      second run 415bf0bc NOOP inserted 0 and updated 0, canonical counts unchanged, 220 records across 7 entity types with 220 distinct source identities
verify-layer1: K-L  validation        PASS      run 38707968 PARTIAL_SUCCESS: 3 records quarantined with 6 structured errors over 3 source ids, 4 valid fixture records still queryable, no source values disclosed
verify-layer1: M    connector_health  PASS      3 configured sources healthy and read-only: csv_demo, odoo_mock, rest_mock
verify-layer1: A-M  read_only         PASS      14 source files byte-identical (sha256) after the scenario
verify-layer1: N    test_suite        SKIPPED   not run; pass --with-tests, or run make test separately
verify-layer1: O    clean_rebuild     OPERATOR  operator step: make docker-down && make docker-build && make docker-up, then run this script again; the dataset, canonical ids and record hashes are deterministic, so the report must be identical
verify-layer1: 8 passed, 0 failed, 1 skipped, 1 operator
```

Run ids differ per run; every count above is reproducible. On a database that already holds the
dataset, step A–C reports how many records it found and steps E–F report `NOOP` with the same
220 records as `unchanged`.

### What each acceptance threshold means and how it is checked

| Threshold | Pass condition | Checked by |
|---|---|---|
| Build | Clean install/build succeeds | `make install`; `make docker-build` |
| Startup | All required services become healthy | `stack_ready` (API + PostgreSQL) and `connector_health` (all three sources); `docker compose ps` shows three healthy containers |
| Migration | Empty PostgreSQL reaches the expected schema | `stack_ready` requires all seven canonical tables to answer; `tests/integration/test_h3_migrations.py` migrates a private empty database to head and compares it to the models column by column |
| Ingestion | The demo dataset reaches the canonical tables with no manual DB edits | `ingestion`: counts balance and every entity's fetched count equals its committed CSV row count |
| Idempotency | No duplicate source identities after repeated ingestion | `idempotency`: the identical run again inserts and updates nothing, the counts do not move, and all seven entity types are swept for duplicate `(source_system, source_entity, source_id)` |
| Traceability | Every accepted record has provenance | `api_query`: every returned record carries `source_system`, `source_entity`, `source_id`, `ingested_at`, `ingestion_run_id` and `record_hash` |
| Validation | The bad fixture produces structured errors and quarantine | `validation`: `PARTIAL_SUCCESS`, structured errors readable at `GET /ingestion/runs/{id}/errors`, and every non-rejected fixture row still queryable |
| API | Canonical records are queryable with pagination | `api_query`: `limit`/`offset` are echoed, `total` is stable across pages and pages do not overlap |
| Safety | No source write operations are executed | `read_only`: all 14 committed source files are byte-identical (SHA-256) after the scenario. Structurally: no connector exposes a write method, no connector module names a mutating HTTP verb, and the live mock source records only `GET` (`tests/contract/`) |
| Tests | All required automated tests pass | `make test` — 4139 tests in four layers; or `make verify-layer1 ARGS="--with-tests"` |
| Reproducibility | A clean rebuild reproduces the same demo behaviour | Step O: `make docker-down && make docker-build && make docker-up`, then run the command again. The dataset regenerates byte-identically, canonical ids are UUID5 of the source identity, and record hashes cover normalized business fields only |
| Documentation | The README enables a new developer to run Layer 1 | [Prerequisites](#prerequisites) → [Environment Setup](#environment-setup) → [Running with Docker Compose](#running-with-docker-compose) or [Running Locally](#running-locally-without-docker) → [Ingestion Commands](#ingestion-commands) → [API Usage Examples](#api-usage-examples) → [Test Commands](#test-commands) |

Steps N and O are the two the command does not perform for you: N needs its own database and runs
only with `--with-tests`, and a script cannot tear down and rebuild the stack it is talking to.

---

## Troubleshooting

### Commands

| Symptom | Cause | Fix |
|---|---|---|
| `make: .venv/bin/pytest: No such file or directory` (or `.venv/bin/python`) | Every target runs the project virtualenv, which is not committed | `make install` |
| `verify_layer1: the Layer 1 API at http://localhost:8000 could not be reached (ConnectError)` | The stack is not running, or the API is on another port | `make docker-up`; otherwise `make verify-layer1 ARGS="--base-url http://host:port"` |
| `seed_demo: stale files: data/demo/...` | The committed dataset no longer matches the generator | `make seed` to rewrite it, then `make docker-build` — both images bake in `data/demo` |
| `ingest_demo: ConnectorConfigurationError: ...` and exit `2` | A bad `--source`, `--data-directory` or `--base-url`; no run was created | Correct the option. `--base-url` applies to the HTTP sources only, `--data-directory` to `csv_demo` only |
| `verify_layer1: invalid logging settings: APP_LOG_LEVEL must be one of ...` | `APP_LOG_LEVEL` or `LOG_FORMAT` is not a supported value | `APP_LOG_LEVEL` is a standard level name; `LOG_FORMAT` is `json` or `text` |

### The stack

| Symptom | Cause | Fix |
|---|---|---|
| `{"detail":"Not Found"}` from a documented route, or a `/api/v1/health` body with no `checks` | The `api` container is running an image built before that route existed | `make docker-build && make docker-up` |
| `GET /api/v1/health` → `503` with `"database": "unavailable"` | PostgreSQL is not reachable from the API | `docker compose ps` — wait for `ai-ceo-postgres` to be healthy; check `DATABASE_URL`/`POSTGRES_*` |
| `relation "customers" does not exist` | The database was never migrated — the API container does not migrate on startup | `make migrate`, or `docker compose exec api alembic upgrade head` |
| Compose fails to start a service with a port error | `5432`, `8000` or `8080` is already bound on the host | Stop the other process, or set `POSTGRES_PORT`/`APP_PORT` in `.env` |
| The database is empty again after a restart | `docker compose down -v` removed the `pgdata` volume | Use `make docker-down` (no `-v`); restore with `make migrate && make ingest-demo` |

### Ingestion and sources

| Symptom | Cause | Fix |
|---|---|---|
| A run of `odoo_mock` or `rest_mock` is `FAILED` with `error_summary: "connector health check failed; N entities skipped"` when started from the host | The committed `base_url` is `http://mock-source:8080`, which only resolves inside the compose network | `make ingest-demo ARGS="--source rest_mock --base-url http://localhost:8080"`. Through the API this does not arise: the API resolves the name inside the network |
| `POST /ingestion/runs` → `422 SOURCE_NOT_FOUND` | The `source` is not in `config/connectors/` | Use one of the names in `details.available_sources` |
| `POST /ingestion/runs` → `422 UNSUPPORTED_OPTION` for `dry_run` | Every Layer 1 run persists its results | Drop the option |
| `422 INVALID_REQUEST` with a `loc` of `["query","limit"]` | `limit` is outside 1–500 (`offset` outside 0–2147483647) | Use a page inside the documented bounds |
| A run is `PARTIAL_SUCCESS` and you expected `SUCCESS` | Records were rejected, or an entity or batch failed | `GET /api/v1/ingestion/runs/{run_id}/errors` — each row names the code, field and source id |
| A second run reports `NOOP` and inserts nothing | Ingestion reconciles on source identity; nothing changed | This is the expected idempotent result, not a failure |
| `deals.customer_id` is `NULL` while `customer_source_id` is set | The referenced customer is not in this source, so the reference stayed unresolved (an `UNRESOLVED_REFERENCE` warning) | Ingest the parent entity first, or accept it — the source key is preserved |
| `employees.organization_id` is always `NULL` | Known gap: the canonical Employee contract carries no organization source key | See [Known Limitations](#known-limitations) |

### Tests

| Symptom | Cause | Fix |
|---|---|---|
| `IntegrityError: duplicate key value violates unique constraint "uq_customers_source_identity"` during a test run | Two pytest sessions are sharing `<database>_test` | Never run two sessions with integration or end-to-end tests at once |
| `tests/integration` or `tests/e2e` fail to connect at session start | No reachable PostgreSQL | `make docker-up`. `pytest tests/unit tests/contract` needs no database at all |
| A test run drops and recreates a database | Expected: the harness recreates `<database>_test` once per session, and the H3 migration tests use a private `<database>_migrations_test` | The harness refuses any database name that does not end in `_test` |

---

## Known Limitations

**Layer 1 is a prototype**, built to demonstrate the connector subsystem end to end on one
machine. It is not production software, and the list below is deliberate scope, not a backlog of
defects. The per-area sections carry the detail: [CSV connector](#current-limitations),
[dataset](#dataset-limitations), [security](#security-limitations) and [API](#api-limitations).

**Scope**

- Layer 1 stops at the canonical relational contract. No knowledge graph, RAG, forecasting,
  multi-agent or human-action layer exists, and none is designed for here.
- No LLM is used anywhere. Every transformation is deterministic, configuration-driven code.

**Sources**

- The three connectors read local sources: committed CSV files and the C3 mock source. No live
  Odoo or third-party REST system is contacted, and no credential is exercised end to end. The
  Odoo and REST adapters implement the real connector contract against a deterministic local
  server, and the boundary is explicit — `odoo_mock` and `rest_mock` are named as mocks in their
  configuration, their source system and the API.
- Full sync only. No connector supports incremental sync, so every run re-reads the whole source;
  `ingestion_cursors` records progress but no connector consumes a cursor across runs.
- No deletes and no cross-source merging. A record removed at the source stays in the canonical
  tables, and the same real-world entity ingested from two sources remains two canonical records.
- CSV only for files: no Excel, and each fetch re-reads the file.

**Data and schema**

- The demo dataset is synthetic and small: 233 rows in all, of which the acceptance scenario
  ingests the 220 belonging to its five entity types. It is sized to be readable, not to show
  scale.
- The canonical vocabulary is narrow by design; richer source values are rejected until the D1
  configuration is extended.
- `employees.organization_id` stays `NULL`: the canonical Employee contract carries no
  organization source key (an open B1/B2 gap recorded in [Dataset limitations](#dataset-limitations)).

**Operations**

- No authentication or authorization. Anyone who can reach the API can start a run, so deploy it
  only on a trusted network.
- Runs are synchronous: `POST /ingestion/runs` holds the connection open for the whole run, with
  no cancellation and no server-side timeout. A run interrupted by a process crash stays
  `RUNNING`.
- Single process, single machine. Counters are per API worker and reset on restart, logs go to
  stderr with no shipping, and there is no Prometheus exposition, no CI pipeline and no
  horizontal scaling.
- Both Docker images bake in `data/demo`, so a regenerated dataset needs `make docker-build`.
- `PyYAML` is imported directly but reaches the environment through `uvicorn[standard]` rather
  than being declared in `pyproject.toml`.
- Known lint and type debt, deliberately left visible rather than silenced: with ruff 0.16.7 and
  mypy 2.3.1, `ruff check app/ tests/ scripts/` reports 69 findings and `mypy app/` reports 9
  errors. All are pre-existing and none changes ingestion behaviour.

See the Layer 1 Master Build Prompt (`CONTEXT/Layer1_Prompt/`) for the full scope definition.

---

## Project Source Documents

- `CONTEXT/INTRODUCTION/AI_CEO_Project_Proposal.pdf`
- `CONTEXT/Layer1_Prompt/AI_CEO_Layer_1_Master_Build_Prompt.pdf`
- `CONTEXT/AI_CEO_PROJECT_CONTEXT.md` — confirmed design decisions and task map
