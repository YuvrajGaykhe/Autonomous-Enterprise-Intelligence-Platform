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

<!-- To be completed in Task A3 and I2 -->

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
