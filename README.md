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

<!-- To be completed in Task E2 and I2 -->

---

## Running with Docker Compose

Start all three services (postgres, api, mock-source):

```bash
make docker-up
# or directly:
docker compose up --build -d
```

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

## Ingestion Commands

<!-- To be completed in Task E1 and I2 -->

---

## API Usage Examples

<!-- To be completed in Task F1/F2 and I2 -->

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
