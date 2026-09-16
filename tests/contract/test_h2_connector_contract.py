"""
H2 connector contract tests (spec Section 15, "Connector contract").

One suite, run against all three configured connectors over the same demo
dataset: the committed CSVs read directly, and the same CSVs served by the C3
mock-source in Odoo and REST shapes. Every test below is parameterized over
all three, so a connector that answers the shared interface differently fails
here even when its own C-task suite still passes.

The contract has four parts:

1. Interface     the protocol's attributes and methods, with the declared
                 return types.
2. Discovery     capabilities() and list_entities() agree with each other and
                 cover every canonical entity type.
3. Traversal     fetch_entities pages deterministically through an entity
                 exactly once, honours page_size, and get_entity round-trips
                 any record a page produced.
4. Read-only     no write method exists on any connector, no connector module
                 names a mutating HTTP verb, and the live mock-source observes
                 nothing but GET.

Failure behaviour is part of the contract too: the same bad argument must
raise the same exception class from every connector.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from conftest import CONTRACT_ENTITIES, CONTRACT_SOURCES, make_connector, source_id_of

from app.connectors.base import SourceConnector
from app.connectors.registry import PROJECT_ROOT
from app.connectors.types import (
    ConnectorCapabilities,
    ConnectorEntityError,
    ConnectorHealth,
    ConnectorRequestError,
    Page,
    SourceEntity,
)

pytestmark = pytest.mark.contract

#: Method names that would let Layer 1 modify a source system.
WRITE_METHOD_NAMES = (
    "create", "update", "delete", "remove", "insert", "upsert", "write",
    "save", "post", "put", "patch", "push", "sync", "set_entity", "execute",
)

#: HTTP verbs no connector may issue (spec Section 5: GET-only).
WRITE_VERBS = ("post", "put", "patch", "delete", "head", "options")

CONNECTOR_MODULES = ("csv.py", "odoo.py", "rest.py", "base.py", "registry.py")


# ---------------------------------------------------------------------------
# 1. Interface
# ---------------------------------------------------------------------------


def test_every_connector_satisfies_the_protocol(connector):
    assert isinstance(connector, SourceConnector)


def test_every_connector_names_itself(connector):
    """source_name maps to canonical source_system, so it must be exact."""
    assert connector.source_name in CONTRACT_SOURCES
    assert isinstance(connector.source_type, str) and connector.source_type


def test_the_identity_of_a_connector_is_read_only(connector):
    """Nothing may repoint a built connector at another source."""
    with pytest.raises(AttributeError):
        connector.source_name = "other"


@pytest.mark.parametrize(
    "method", ["health_check", "list_entities", "fetch_entities", "get_entity", "capabilities"]
)
def test_every_contract_method_is_present_and_callable(connector, method):
    assert callable(getattr(connector, method))


def test_fetch_entities_keeps_the_declared_signature(connector):
    """E1 calls fetch_entities positionally and by keyword; both must work."""
    parameters = list(inspect.signature(connector.fetch_entities).parameters)
    assert parameters == ["entity_type", "cursor", "page_size"]


# ---------------------------------------------------------------------------
# 2. Discovery
# ---------------------------------------------------------------------------


def test_every_connector_declares_itself_read_only(connector):
    capabilities = connector.capabilities()
    assert isinstance(capabilities, ConnectorCapabilities)
    assert capabilities.read_only is True


def test_every_connector_offers_every_canonical_entity_type(connector):
    """Layer 2 consumes the same seven entities regardless of source."""
    assert sorted(connector.capabilities().supported_entity_types) == sorted(CONTRACT_ENTITIES)


def test_list_entities_agrees_with_capabilities(connector):
    entities = connector.list_entities()
    assert all(isinstance(entity, SourceEntity) for entity in entities)
    assert sorted(entity.entity_type for entity in entities) == sorted(
        connector.capabilities().supported_entity_types
    )


def test_health_check_reports_this_source(connector):
    health = connector.health_check()
    assert isinstance(health, ConnectorHealth)
    assert health.healthy is True
    assert health.source_name == connector.source_name


def test_a_connector_that_declares_health_support_answers_health_checks(connector):
    """The capability flag and the method must not disagree."""
    if connector.capabilities().supports_health_check:
        assert connector.health_check().healthy is True


# ---------------------------------------------------------------------------
# 3. Traversal
# ---------------------------------------------------------------------------


def _drain(connector, entity_type: str, page_size: int) -> list[dict]:
    """Walk every page of an entity, asserting the cursor always advances."""
    records: list[dict] = []
    cursor: str | None = None
    seen_cursors: set[str | None] = set()
    for _ in range(1000):
        page = connector.fetch_entities(entity_type, cursor, page_size)
        assert isinstance(page, Page)
        assert isinstance(page.items, list)
        assert len(page.items) <= page_size
        records.extend(page.items)
        if not page.has_more:
            return records
        assert page.next_cursor is not None
        assert page.next_cursor not in seen_cursors, "cursor repeated; traversal would not end"
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor
    raise AssertionError("pagination did not terminate")


@pytest.mark.parametrize("entity_type", CONTRACT_ENTITIES)
def test_every_entity_type_can_be_fetched(connector, entity_type):
    page = connector.fetch_entities(entity_type, None, 5)
    assert isinstance(page, Page)
    assert all(isinstance(record, dict) for record in page.items)


@pytest.mark.parametrize("page_size", [1, 3, 500])
def test_pagination_returns_every_record_exactly_once(connector, page_size):
    """The page size changes the number of requests, never the result set."""
    records = _drain(connector, "customers", page_size)
    ids = [source_id_of(connector, "customers", record) for record in records]
    assert len(ids) == len(set(ids)), "pagination repeated a record"
    assert len(ids) == 50, "the demo dataset has 50 customers (spec Section 12)"


def test_pagination_is_independent_of_page_size(connector):
    """One page of 500 and fifty pages of 1 must agree, in the same order."""
    whole = [source_id_of(connector, "customers", r) for r in _drain(connector, "customers", 500)]
    piecewise = [source_id_of(connector, "customers", r) for r in _drain(connector, "customers", 1)]
    assert whole == piecewise


def test_fetching_is_deterministic(connector):
    """Same request, same answer: re-ingestion must not reshuffle records."""
    first = connector.fetch_entities("deals", None, 10)
    second = connector.fetch_entities("deals", None, 10)
    assert first.items == second.items
    assert (first.next_cursor, first.has_more) == (second.next_cursor, second.has_more)


def test_the_final_page_closes_the_traversal(connector):
    """has_more is False exactly once, on the page that ends the entity."""
    page = connector.fetch_entities("organizations", None, 500)
    assert page.has_more is False
    assert page.next_cursor is None


def test_get_entity_round_trips_a_record_from_a_page(connector):
    """A record a page produced must be retrievable by its source id."""
    record = connector.fetch_entities("customers", None, 1).items[0]
    assert connector.get_entity("customers", source_id_of(connector, "customers", record)) == record


def test_get_entity_round_trips_every_record_of_a_small_entity(connector):
    """Not just the first: every source id a page exposed must resolve."""
    for record in _drain(connector, "organizations", 500):
        source_id = source_id_of(connector, "organizations", record)
        assert connector.get_entity("organizations", source_id) == record


# ---------------------------------------------------------------------------
# 3b. Failure behaviour is part of the contract
# ---------------------------------------------------------------------------


def test_an_unknown_entity_type_is_refused_identically(connector):
    with pytest.raises(ConnectorEntityError):
        connector.fetch_entities("not_an_entity", None, 10)


def test_an_unknown_entity_type_is_refused_by_get_entity_too(connector):
    with pytest.raises(ConnectorEntityError):
        connector.get_entity("not_an_entity", "1")


def test_an_unknown_source_id_is_refused_identically(connector):
    with pytest.raises(ConnectorEntityError):
        connector.get_entity("customers", "no-such-record")


@pytest.mark.parametrize("cursor", ["abc", "-1", "1.5", ""])
def test_a_malformed_cursor_is_refused_identically(connector, cursor):
    with pytest.raises(ConnectorRequestError):
        connector.fetch_entities("customers", cursor, 10)


@pytest.mark.parametrize("page_size", [0, -1])
def test_a_non_positive_page_size_is_refused_identically(connector, page_size):
    with pytest.raises(ConnectorRequestError):
        connector.fetch_entities("customers", None, page_size)


def test_a_cursor_past_the_end_returns_an_empty_final_page(connector):
    """Not an error: an exhausted source ends the loop rather than failing."""
    page = connector.fetch_entities("organizations", "10000", 10)
    assert (page.items, page.has_more) == ([], False)


# ---------------------------------------------------------------------------
# 4. Read-only
# ---------------------------------------------------------------------------


def test_no_connector_exposes_a_write_method(connector):
    """Layer 1 never writes back to a source (spec Sections 3 and 14)."""
    public = [name for name in dir(connector) if not name.startswith("_")]
    offenders = [
        name for name in public
        if any(word in name.lower() for word in WRITE_METHOD_NAMES)
    ]
    assert offenders == []


def test_the_protocol_itself_declares_no_write_method():
    """A write method added to the contract would spread to every connector."""
    declared = [name for name in dir(SourceConnector) if not name.startswith("_")]
    assert sorted(declared) == [
        "capabilities", "fetch_entities", "get_entity",
        "health_check", "list_entities", "source_name", "source_type",
    ]


@pytest.mark.parametrize("module", CONNECTOR_MODULES)
def test_no_connector_module_issues_a_mutating_http_verb(module):
    """A static check: an HTTP client call other than GET must not appear."""
    source = (PROJECT_ROOT / "app" / "connectors" / module).read_text(encoding="utf-8")
    for verb in WRITE_VERBS:
        assert f".{verb}(" not in source, f"{module} calls .{verb}()"
        assert f'"{verb.upper()}"' not in source, f"{module} names {verb.upper()}"


def test_http_connectors_only_ever_issue_get(mock_source_url, requests_seen):
    """Runtime proof: the live source observes GET and nothing else."""
    for source in ("odoo_mock", "rest_mock"):
        connector = make_connector(source, mock_source_url)
        connector.health_check()
        page = connector.fetch_entities("customers", None, 5)
        connector.get_entity("customers", source_id_of(connector, "customers", page.items[0]))

    assert requests_seen, "the mock-source recorded no requests"
    assert {method for method, _ in requests_seen} == {"GET"}


def test_reading_a_source_never_changes_it(connector):
    """Two full traversals separated by a lookup return identical records."""
    before = _drain(connector, "projects", 500)
    connector.get_entity("projects", source_id_of(connector, "projects", before[0]))
    assert _drain(connector, "projects", 500) == before


def test_the_csv_source_files_are_never_opened_for_writing(csv_connector, tmp_path):
    """The CSV connector reads the committed demo files in place."""
    demo = PROJECT_ROOT / "data" / "demo"
    before = {path.name: path.stat().st_mtime_ns for path in sorted(demo.glob("*.csv"))}
    csv_connector.health_check()
    csv_connector.fetch_entities("customers", None, 500)
    after = {path.name: path.stat().st_mtime_ns for path in sorted(demo.glob("*.csv"))}
    assert before == after


def test_every_connector_module_lives_behind_the_shared_contract():
    """No connector module may import persistence or canonical schemas."""
    for module in ("csv.py", "odoo.py", "rest.py"):
        source = (PROJECT_ROOT / "app" / "connectors" / module).read_text(encoding="utf-8")
        assert "app.persistence" not in source
        assert "app.schemas.canonical" not in source


def test_the_demo_directory_the_contract_reads_is_the_committed_one():
    """Guards the suite itself: these tests must exercise real demo data."""
    demo = Path(PROJECT_ROOT / "data" / "demo")
    assert sorted(path.name for path in demo.glob("*.csv")) == [
        f"{entity}.csv" for entity in sorted(CONTRACT_ENTITIES)
    ]
