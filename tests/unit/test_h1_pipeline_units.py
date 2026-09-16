"""
H1 unit tests — orchestration, persistence and pagination helpers.

Spec Section 15 requires unit coverage of pagination helpers, and the E1
suites exercise orchestration only through a live database. This module
covers the pure surfaces that need neither PostgreSQL nor a connector:

1. The connector-page contract the orchestrator enforces on every fetch. It
   is the boundary between a third-party connector and the ingestion loop,
   so each rule is asserted separately and by message.
2. QueryPage, the limit/offset page every list endpoint returns.
3. The timezone guards the run-scoped repositories apply before they touch
   the session, so a naive timestamp can never be written.
4. The session factory the application and scripts share.

These tests must stay database-free: the guards they cover run before any
statement is executed, and that is exactly what they assert.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.connectors import Page
from app.core.database import get_session_factory
from app.ingestion.errors import ConnectorContractError
from app.ingestion.orchestrator import _page_items
from app.persistence.repositories import cursors, errors
from app.persistence.repositories.run_queries import QueryPage

RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000009")
AWARE = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
NAIVE = datetime(2026, 9, 16, 12, 0)


# ---------------------------------------------------------------------------
# Connector page contract
# ---------------------------------------------------------------------------


def test_a_well_formed_final_page_is_accepted():
    page = Page(items=[{"id": "1"}], next_cursor=None, has_more=False)
    assert _page_items(page, None, 100) == [{"id": "1"}]


def test_a_well_formed_intermediate_page_is_accepted():
    page = Page(items=[{"id": "1"}], next_cursor="1", has_more=True)
    assert _page_items(page, None, 1) == [{"id": "1"}]


def test_an_empty_page_is_accepted():
    assert _page_items(Page(items=[], has_more=False), None, 10) == []


@pytest.mark.parametrize("returned", [None, [], {"items": []}, "page"])
def test_fetch_entities_must_return_a_page(returned):
    """A connector that returns some other shape is named in the failure."""
    with pytest.raises(ConnectorContractError) as exc:
        _page_items(returned, None, 10)
    assert f"returned {type(returned).__name__}, not Page" in str(exc.value)


@pytest.mark.parametrize("items", [None, "abc", {"a": 1}, ({"id": "1"},)])
def test_page_items_must_be_a_list(items):
    """Anything iterable-but-not-a-list would silently change batch ordering."""
    page = Page(items=items, has_more=False)
    with pytest.raises(ConnectorContractError, match="Page.items must be a list"):
        _page_items(page, None, 10)


def test_a_page_may_not_exceed_the_requested_page_size():
    """Oversized pages would break the bounded-batch transaction policy."""
    page = Page(items=[{"id": "1"}, {"id": "2"}, {"id": "3"}], has_more=False)
    with pytest.raises(ConnectorContractError, match="more records than the requested page_size"):
        _page_items(page, None, 2)


def test_a_page_exactly_at_the_page_size_is_accepted():
    page = Page(items=[{"id": "1"}, {"id": "2"}], has_more=False)
    assert len(_page_items(page, None, 2)) == 2


@pytest.mark.parametrize("has_more", [None, 1, 0, "true"])
def test_has_more_must_be_a_bool(has_more):
    """Truthy values are rejected: the loop's exit condition must be exact."""
    page = Page(items=[], next_cursor="1", has_more=has_more)
    with pytest.raises(ConnectorContractError, match="Page.has_more must be a bool"):
        _page_items(page, None, 10)


@pytest.mark.parametrize("next_cursor", [None, 5, "same"])
def test_a_page_claiming_more_records_must_advance_the_cursor(next_cursor):
    """A repeated or missing cursor would make the fetch loop spin forever."""
    page = Page(items=[{"id": "1"}], next_cursor=next_cursor, has_more=True)
    with pytest.raises(ConnectorContractError, match="without advancing the cursor"):
        _page_items(page, "same", 10)


def test_a_final_page_needs_no_cursor():
    """has_more=False frees the connector from supplying a next cursor."""
    page = Page(items=[{"id": "1"}], next_cursor="same", has_more=False)
    assert _page_items(page, "same", 10) == [{"id": "1"}]


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------


def test_a_page_reports_the_total_independently_of_its_items():
    """total is the matching row count, not the size of this slice."""
    page = QueryPage(items=["a", "b"], total=57)
    assert (page.items, page.total) == (["a", "b"], 57)


def test_an_empty_page_can_still_report_a_total():
    """An offset past the end returns no items but the unchanged total."""
    assert QueryPage(items=[], total=57).total == 57


def test_a_page_is_immutable():
    """Callers cannot rewrite a page's total after the query answered."""
    page = QueryPage(items=[], total=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        page.total = 1


def test_pages_with_equal_contents_are_equal():
    assert QueryPage(items=["a"], total=1) == QueryPage(items=["a"], total=1)
    assert QueryPage(items=["a"], total=1) != QueryPage(items=["a"], total=2)


# ---------------------------------------------------------------------------
# Timezone guards run before any statement
# ---------------------------------------------------------------------------


def test_a_checkpoint_refuses_a_naive_timestamp():
    """The guard fires before the session is used, so None is safe here."""
    with pytest.raises(ValueError, match="updated_at must be timezone-aware"):
        cursors.record_entity_success(None, source_system="csv_demo",
                                      source_entity="customers", run_id=RUN_ID,
                                      last_cursor=None, updated_at=NAIVE)


def test_error_rows_refuse_a_naive_timestamp():
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        errors.add_errors(None, RUN_ID, [], created_at=NAIVE)


@pytest.mark.parametrize(
    "moment",
    [AWARE, datetime(2026, 9, 16, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))],
)
def test_any_aware_timestamp_passes_the_guard(moment):
    """The guard checks awareness only; UTC conversion is the column's job."""
    with pytest.raises(AttributeError):
        # Passes the guard, then fails on the absent session.
        cursors.record_entity_success(None, source_system="csv_demo",
                                      source_entity="customers", run_id=RUN_ID,
                                      last_cursor=None, updated_at=moment)


def test_no_error_rows_still_validates_the_timestamp_first():
    """An empty batch must not become a silent way past the guard."""
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        errors.add_errors(None, RUN_ID, (), created_at=NAIVE)


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------


def test_the_session_factory_is_bound_and_configured_for_layer_1():
    """Sessions keep loaded attributes after commit, as the repositories expect."""
    factory = get_session_factory()
    assert isinstance(factory, sessionmaker)
    assert issubclass(factory.class_, Session)
    assert factory.kw["expire_on_commit"] is False
    assert factory.kw["bind"] is not None


def test_the_session_factory_engine_never_echoes_sql_or_parameters():
    """G2 secret hygiene: bound parameters must not reach logs (spec 14)."""
    engine = get_session_factory().kw["bind"]
    assert engine.echo is False
    assert engine.hide_parameters is True
