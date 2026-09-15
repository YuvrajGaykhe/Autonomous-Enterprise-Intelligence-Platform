"""
Docker packaging contract: the images contain everything the runtime resolves.

The API resolves its configuration and the csv_demo dataset relative to the
project root (/app in the image), and the API and mock-source images both bake
in the committed data/demo dataset. These checks keep the Dockerfiles,
.dockerignore and docker-compose.yml aligned with those runtime paths without
needing Docker.
"""

from __future__ import annotations

import shlex
from pathlib import Path, PurePosixPath

import yaml

from app.connectors import registry
from app.normalization.config import DEFAULT_CONFIG_DIR
from app.validation.config import DEFAULT_CONFIG_PATH

REPO = Path(__file__).resolve().parents[2]
API_DOCKERFILE = REPO / "Dockerfile"
MOCK_DOCKERFILE = REPO / "docker" / "Dockerfile.mock-source"
IMAGE_ROOT = PurePosixPath("/app")


def _instructions(path: Path) -> list[tuple[str, str]]:
    instructions, pending = [], ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not pending and (not line or line.startswith("#")):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        keyword, _, arguments = (pending + line).partition(" ")
        instructions.append((keyword.upper(), arguments.strip()))
        pending = ""
    return instructions


def _copies(path: Path) -> list[tuple[str, str]]:
    copies = []
    for keyword, arguments in _instructions(path):
        if keyword == "COPY":
            source, destination = shlex.split(arguments)
            copies.append((source, destination))
    return copies


def _compose() -> dict:
    return yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))


def _copied(path: Path, copies: list[tuple[str, str]]) -> bool:
    relative = path.relative_to(REPO).as_posix()
    return any(relative == source.rstrip("/") or relative.startswith(source.rstrip("/") + "/")
               for source, _ in copies)


def _connector_config(name: str) -> dict:
    return yaml.safe_load((registry.CONNECTOR_CONFIG_DIR / name).read_text(encoding="utf-8"))


def test_the_api_image_runs_the_app_from_the_project_root():
    instructions = _instructions(API_DOCKERFILE)
    assert ("WORKDIR", str(IMAGE_ROOT)) in instructions
    assert ("CMD", '["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]') in \
        instructions
    assert registry.PROJECT_ROOT == REPO


def test_api_copies_mirror_the_repository_layout():
    for source, destination in _copies(API_DOCKERFILE):
        expected = f"./{source}" if (REPO / source).is_dir() else "./"
        assert destination == expected, source


def test_the_api_image_contains_exactly_the_runtime_files():
    assert {source for source, _ in _copies(API_DOCKERFILE)} == {
        "pyproject.toml", "app/", "config/", "data/demo/", "alembic.ini", "migrations/"}


def test_every_path_the_api_resolves_at_runtime_is_copied_into_the_image():
    csv_config = _connector_config(registry.SOURCE_CONFIG_FILES["csv_demo"])
    data_directory = registry.PROJECT_ROOT / csv_config["data_directory"]
    runtime_paths = [
        REPO / "app" / "main.py",
        *(registry.CONNECTOR_CONFIG_DIR / name for name in registry.SOURCE_CONFIG_FILES.values()),
        DEFAULT_CONFIG_DIR,
        DEFAULT_CONFIG_PATH,
        *(data_directory / entity["file"] for entity in csv_config["entities"].values()),
        REPO / "alembic.ini",
        REPO / "migrations" / "env.py",
    ]
    copies = _copies(API_DOCKERFILE)
    for path in runtime_paths:
        assert path.exists(), path
        assert _copied(path, copies), path


def test_the_api_image_excludes_test_fixtures_scripts_and_local_state():
    copies = _copies(API_DOCKERFILE)
    for path in (REPO / "data" / "fixtures" / "csv_demo_bad", REPO / "tests", REPO / "scripts",
                 REPO / "CONTEXT", REPO / "docker", REPO / ".env.example"):
        assert not _copied(path, copies), path


def test_the_mock_source_serves_the_dataset_the_csv_connector_reads():
    csv_config = _connector_config(registry.SOURCE_CONFIG_FILES["csv_demo"])
    image_dataset = str(IMAGE_ROOT / csv_config["data_directory"])
    assert ("data/demo/", "./data/demo/") in _copies(MOCK_DOCKERFILE)
    assert ("data/demo/", "./data/demo/") in _copies(API_DOCKERFILE)
    assert ("WORKDIR", str(IMAGE_ROOT)) in _instructions(MOCK_DOCKERFILE)
    environment = dict(_instructions(MOCK_DOCKERFILE))["ENV"]
    assert f"MOCK_SOURCE_DATA_DIR={image_dataset}" in environment
    assert _compose()["services"]["mock-source"]["environment"]["MOCK_SOURCE_DATA_DIR"] == \
        image_dataset


def test_http_connectors_target_the_compose_mock_source_service():
    services = _compose()["services"]
    port = services["mock-source"]["environment"]["MOCK_SOURCE_PORT"]
    expected = f"http://mock-source:{port}"
    for source in ("odoo_mock", "rest_mock"):
        assert _connector_config(registry.SOURCE_CONFIG_FILES[source])["base_url"] == expected
    assert services["api"]["environment"]["MOCK_SOURCE_BASE_URL"] == expected


def test_compose_services_use_no_host_bind_mounts():
    compose = _compose()
    for name, service in compose["services"].items():
        for volume in service.get("volumes", []):
            source = volume.split(":", 1)[0]
            assert source in compose["volumes"], f"{name}: {volume}"
    assert "volumes" not in compose["services"]["api"]
    assert "volumes" not in compose["services"]["mock-source"]


def test_the_api_waits_for_postgres_and_probes_readiness():
    api = _compose()["services"]["api"]
    assert api["depends_on"]["postgres"] == {"condition": "service_healthy"}
    assert "/api/v1/health" in " ".join(api["healthcheck"]["test"])
    assert "@postgres:5432/" in api["environment"]["DATABASE_URL"]


def test_the_build_context_excludes_secrets_and_local_state():
    entries = {line.strip() for line in (REPO / ".dockerignore").read_text(encoding="utf-8")
               .splitlines() if line.strip() and not line.startswith("#")}
    assert entries >= {".git", ".env", ".env.local", ".env.*.local", ".venv", "venv",
                       ".pytest_cache", ".mypy_cache", ".ruff_cache", "CONTEXT", "data/raw",
                       "data/quarantine"}
    # Patterns match from the context root, so nested caches need the ** prefix.
    assert entries >= {"**/__pycache__", "**/*.pyc", "**/*.pyo", "**/.DS_Store"}
    for required in ("app", "config", "data", "data/demo", "migrations", "alembic.ini",
                     "pyproject.toml", "docker"):
        assert required not in entries and f"{required}/" not in entries
