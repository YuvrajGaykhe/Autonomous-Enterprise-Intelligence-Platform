# =============================================================================
# AI CEO — Layer 1 Makefile
# All commands are documented in README.md.
# =============================================================================

.PHONY: help install migrate migration-status seed ingest-demo test lint format \
        secret-scan verify-layer1 docker-up docker-down docker-build clean

# Default target: show available commands.
help:
	@echo ""
	@echo "AI CEO — Layer 1 Commands"
	@echo "========================================"
	@echo "  make install         Install Python dependencies into virtualenv"
	@echo "  make migrate         Run Alembic migrations (upgrade to head)"
	@echo "  make migration-status Show current Alembic revision and history"
	@echo "  make seed            Generate the deterministic demo dataset (data/demo)"
	@echo "  make ingest-demo     Run full ingestion of demo CSV data"
	@echo "  make test            Run the full test suite"
	@echo "  make lint            Run ruff + mypy linting"
	@echo "  make format          Run black + ruff --fix formatting"
	@echo "  make secret-scan     Scan tracked files for committed secrets"
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

# Run database migrations.
migrate:
	@echo "[migrate] Running Alembic migrations..."
	.venv/bin/alembic upgrade head
	@echo "[migrate] Done."

# Show current migration revision and history.
migration-status:
	@echo "[migration-status] Current revision:"
	@.venv/bin/alembic current
	@echo ""
	@echo "[migration-status] Migration history:"
	@.venv/bin/alembic history --verbose

# Regenerate the deterministic demo CSV dataset (byte-identical on every run).
# It writes files only; load them with make ingest-demo. ARGS="--check" verifies.
seed:
	@echo "[seed] Generating demo dataset..."
	.venv/bin/python scripts/seed_demo.py $(ARGS)

# Run a full csv_demo ingestion (idempotent: repeating it is a NOOP).
# Pass options through ARGS, e.g. make ingest-demo ARGS="--entities customers deals".
ingest-demo:
	@echo "[ingest-demo] Running ingestion..."
	.venv/bin/python scripts/ingest_demo.py $(ARGS)

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

# Scan every tracked file for committed secrets (G2). Declared and documented
# since G2, but never given a recipe, so it silently did nothing.
secret-scan:
	@echo "[secret-scan] Scanning tracked files..."
	.venv/bin/python scripts/secret_scan.py

# Run the full Layer 1 acceptance scenario (spec Section 20) against a running
# stack. Needs make docker-up first. Pass options through ARGS, e.g.
# make verify-layer1 ARGS="--with-tests".
verify-layer1:
	@echo "[verify-layer1] Running Layer 1 acceptance scenario..."
	.venv/bin/python scripts/verify_layer1.py $(ARGS)

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
