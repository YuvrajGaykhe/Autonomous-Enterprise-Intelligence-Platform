# =============================================================================
# AI CEO — Layer 1 Makefile
# All commands are documented in README.md.
# Targets marked [STUB] will be implemented in their respective tasks.
# =============================================================================

.PHONY: help install migrate seed ingest-demo test lint format verify-layer1 \
        docker-up docker-down docker-build clean

# Default target: show available commands.
help:
	@echo ""
	@echo "AI CEO — Layer 1 Commands"
	@echo "========================================"
	@echo "  make install         Install Python dependencies into virtualenv"
	@echo "  make migrate         Run Alembic migrations on the configured database"
	@echo "  make seed            Seed the database with the deterministic demo organization"
	@echo "  make ingest-demo     Run full ingestion of demo CSV data"
	@echo "  make test            Run the full test suite"
	@echo "  make lint            Run ruff + mypy linting"
	@echo "  make format          Run black + ruff --fix formatting"
	@echo "  make verify-layer1   Run the complete Layer 1 acceptance scenario"
	@echo "  make docker-up       Start all services with Docker Compose"
	@echo "  make docker-down     Stop and remove Docker Compose services"
	@echo "  make docker-build    Rebuild Docker images"
	@echo "  make clean           Remove build artifacts and caches"
	@echo ""

# Install dependencies.
install:
	@echo "[install] Creating virtualenv and installing dependencies..."
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"
	@echo "[install] Done. Activate with: source .venv/bin/activate"

# Run database migrations. [STUB — implemented in Task A3]
migrate:
	@echo "[migrate] Running Alembic migrations... [STUB: Task A3]"
	@echo "  Run: alembic upgrade head"

# Seed demo organization and reference data. [STUB — implemented in Task E2]
seed:
	@echo "[seed] Seeding demo data... [STUB: Task E2]"
	@echo "  Run: python scripts/seed_demo.py"

# Run full demo ingestion. [STUB — implemented in Task E1]
ingest-demo:
	@echo "[ingest-demo] Running demo ingestion... [STUB: Task E1]"
	@echo "  Run: python scripts/ingest_demo.py"

# Run the full test suite.
test:
	@echo "[test] Running test suite..."
	.venv/bin/pytest

# Run linting.
lint:
	@echo "[lint] Running ruff and mypy..."
	.venv/bin/ruff check app/ tests/
	.venv/bin/mypy app/

# Run formatting.
format:
	@echo "[format] Running black and ruff --fix..."
	.venv/bin/black app/ tests/
	.venv/bin/ruff check --fix app/ tests/

# Run the full Layer 1 acceptance scenario. [STUB — implemented in Task I1]
verify-layer1:
	@echo "[verify-layer1] Running Layer 1 acceptance scenario... [STUB: Task I1]"
	@echo "  Run: python scripts/verify_layer1.py"

# Start all Docker Compose services.
docker-up:
	@echo "[docker-up] Starting services..."
	docker compose up --build -d
	@echo "[docker-up] Services started. Run 'docker compose ps' to check status."

# Stop Docker Compose services.
docker-down:
	@echo "[docker-down] Stopping services..."
	docker compose down
	@echo "[docker-down] Services stopped."

# Rebuild Docker images.
docker-build:
	@echo "[docker-build] Rebuilding images..."
	docker compose build
	@echo "[docker-build] Images rebuilt."

# Remove build artifacts.
clean:
	@echo "[clean] Removing build artifacts and caches..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "[clean] Done."
