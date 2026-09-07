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
