"""
E2 demo dataset tests: scripts/seed_demo.py and the committed data files.

Dataset invariants are checked on generated files read back through the C2 CSV
connector (what E1 ingests), for the committed seed and two others so that no
invariant holds only by luck of one seed. The golden tests tie the committed
data/demo and bad fixture files to the generator byte for byte.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.connectors.csv import CsvConnector, CsvConnectorConfig
from app.validation import default_validation_config, validate_source_batch

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
BAD_FIXTURE_DIR = REPO / "data" / "fixtures" / "csv_demo_bad"
ENTITIES = ("organizations", "employees", "customers", "deals", "projects", "support_tickets",
            "documents")
SOURCES = ("csv_demo", "odoo_mock", "rest_mock")
RUN_ID = uuid.UUID("00000000-0000-0000-0000-00000000e2e2")
INGESTED_AT = datetime(2026, 9, 14, tzinfo=UTC)
DELIVERY_TITLES = ("Delivery Lead", "Senior Engineer", "Data Engineer")

sys.path.insert(0, str(REPO / "docker"))
import mock_source  # noqa: E402


def _load_script():
    spec = importlib.util.spec_from_file_location("seed_demo", REPO / "scripts" / "seed_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_demo = _load_script()
AS_OF: date = seed_demo.AS_OF
SEEDS = (seed_demo.SEED, 7, 2027)


def _connector(directory: Path) -> CsvConnector:
    config = CsvConnectorConfig.from_yaml(REPO / "config" / "connectors" / "csv_demo.yaml")
    config.data_directory = str(directory)
    return CsvConnector(config)


def _read(directory: Path) -> dict[str, list[dict[str, str]]]:
    connector = _connector(directory)
    return {entity: connector.fetch_entities(entity, page_size=10_000).items
            for entity in ENTITIES}


def _generate(root: Path, *extra: str) -> int:
    """Run the command line with both outputs under root (never the repository)."""
    return seed_demo.main(["--demo-dir", str(root / "demo"),
                           "--bad-fixture-dir", str(root / "bad"), *extra])


def _day(value: str) -> date:
    return date.fromisoformat(value)


def _rupees(deal: dict[str, str]) -> Decimal:
    return Decimal(deal["amount"]) * seed_demo.RUPEES_PER_UNIT[deal["currency"]]


def _ids(rows: list[dict[str, str]]) -> set[str]:
    return {next(iter(row.values())) for row in rows}


@pytest.fixture(scope="module")
def cli_root(tmp_path_factory) -> Path:
    """Files written by the command line with the committed seed."""
    root = tmp_path_factory.mktemp("cli")
    assert _generate(root) == 0
    return root


@pytest.fixture(scope="module", params=SEEDS, ids=lambda seed: f"seed{seed}")
def generated_dir(request, tmp_path_factory) -> Path:
    directory = tmp_path_factory.mktemp(f"seed{request.param}")
    files = seed_demo.render_dataset(seed_demo.build_demo_dataset(request.param))
    for name, content in files.items():
        (directory / name).write_bytes(content)
    return directory


@pytest.fixture(scope="module")
def data(generated_dir) -> dict[str, list[dict[str, str]]]:
    return _read(generated_dir)


@pytest.fixture(scope="module")
def by_id(data) -> dict[str, dict[str, dict[str, str]]]:
    return {entity: {next(iter(row.values())): row for row in rows}
            for entity, rows in data.items()}


@pytest.fixture(scope="module")
def bad(cli_root) -> dict[str, list[dict[str, str]]]:
    return _read(cli_root / "bad")


def _active_staff(data, *titles: str) -> set[str]:
    return {row["employee_id"] for row in data["employees"]
            if row["title"] in titles and row["is_active"] == "true"}


# ---------------------------------------------------------------------------
# Determinism, the command line and the committed files
# ---------------------------------------------------------------------------


def test_generation_is_byte_identical_across_runs(cli_root, tmp_path):
    assert _generate(tmp_path) == 0
    for output in ("demo", "bad"):
        names = sorted(path.name for path in (cli_root / output).iterdir())
        assert names == sorted(f"{entity}.csv" for entity in ENTITIES)
        for name in names:
            assert (tmp_path / output / name).read_bytes() == (cli_root / output / name).read_bytes()


def test_committed_files_match_the_generator(cli_root, capsys):
    for committed, output in ((DEMO_DIR, "demo"), (BAD_FIXTURE_DIR, "bad")):
        for entity in ENTITIES:
            name = f"{entity}.csv"
            assert (committed / name).read_bytes() == (cli_root / output / name).read_bytes(), name
    capsys.readouterr()
    assert seed_demo.main(["--check"]) == 0
    assert capsys.readouterr().out == "seed_demo: 14 files up to date\n"


def test_check_reports_stale_and_missing_files_without_writing(cli_root, tmp_path, capsys):
    shutil.copytree(cli_root, tmp_path, dirs_exist_ok=True)
    capsys.readouterr()
    assert _generate(tmp_path, "--check") == 0
    assert capsys.readouterr().out == "seed_demo: 14 files up to date\n"
    (tmp_path / "demo" / "deals.csv").write_bytes(b"deal_id\n")
    (tmp_path / "bad" / "documents.csv").unlink()
    capsys.readouterr()

    assert _generate(tmp_path, "--check") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (f"seed_demo: stale files: {tmp_path / 'demo' / 'deals.csv'}, "
                            f"{tmp_path / 'bad' / 'documents.csv'}\n")
    assert (tmp_path / "demo" / "deals.csv").read_bytes() == b"deal_id\n"
    assert not (tmp_path / "bad" / "documents.csv").exists()


def test_write_creates_directories_and_prints_record_counts(tmp_path, capsys):
    root = tmp_path / "nested"
    capsys.readouterr()
    assert _generate(root) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary == {
        "demo": {"directory": str(root / "demo"), "records": {
            "organizations": 1, "employees": 24, "customers": 50, "deals": 44, "projects": 22,
            "support_tickets": 80, "documents": 12}},
        "bad_fixture": {"directory": str(root / "bad"), "records": {
            "organizations": 0, "employees": 0, "customers": 4, "deals": 4, "projects": 0,
            "support_tickets": 0, "documents": 0}},
    }
    assert (root / "demo" / "customers.csv").read_bytes().startswith(b"customer_id,customer_name,")


def test_generation_depends_only_on_the_seed():
    assert seed_demo.build_demo_dataset() == seed_demo.build_demo_dataset(seed_demo.SEED)
    assert seed_demo.build_demo_dataset(seed_demo.SEED + 1) != seed_demo.build_demo_dataset()


def test_generation_is_total_and_structurally_sound_for_many_seeds():
    """No selection may depend on a lucky seed (cheap checks without the CSV round trip)."""
    for seed in range(200):
        dataset = seed_demo.build_demo_dataset(seed)
        created = {row["customer_id"]: row["created_date"] for row in dataset["customers"]}
        titles = [row["title"] for row in dataset["documents"]]
        assert len(set(titles)) == len(titles), seed
        for row in dataset["deals"]:
            if row["stage"] == "won":
                assert created[row["customer_id"]] < row["expected_close_date"] < AS_OF.isoformat()


def test_files_use_the_csv_demo_columns_and_newline_endings(generated_dir, cli_root):
    for directory in (generated_dir, cli_root / "bad"):
        for entity in ENTITIES:
            content = (directory / f"{entity}.csv").read_bytes()
            assert content.decode("ascii").split("\n", 1)[0] == ",".join(seed_demo.COLUMNS[entity])
            assert b"\r" not in content and content.endswith(b"\n")


def test_unknown_arguments_are_rejected():
    with pytest.raises(SystemExit) as caught:
        seed_demo.parse_args(["--seed", "7"])
    assert caught.value.code == 2


# ---------------------------------------------------------------------------
# Spec Section 12 volume and identity
# ---------------------------------------------------------------------------


def test_minimum_volumes_and_single_organization(data):
    counts = {entity: len(rows) for entity, rows in data.items()}
    assert counts == {"organizations": 1, "employees": 24, "customers": 50, "deals": 44,
                      "projects": 22, "support_tickets": 80, "documents": 12}
    minimums = {"employees": 20, "customers": 50, "deals": 40, "projects": 20,
                "support_tickets": 75, "documents": 10}
    assert all(counts[entity] >= minimum for entity, minimum in minimums.items())
    assert data["organizations"] == [{"organization_id": "ORG-001", "organization_name": "Acme Corp",
                                      "industry": "Technology", "country": "India",
                                      "status": "active"}]


@pytest.mark.parametrize(("entity", "prefix"), [
    ("organizations", "ORG"), ("employees", "EMP"), ("customers", "CUST"), ("deals", "DEAL"),
    ("projects", "PROJ"), ("support_tickets", "TKT"), ("documents", "DOC"),
])
def test_identifiers_are_sequential_and_map_to_distinct_odoo_ids(data, entity, prefix):
    ids = [next(iter(row.values())) for row in data[entity]]
    assert ids == [f"{prefix}-{number:03d}" for number in range(1, len(ids) + 1)]
    assert len({mock_source._to_int(value) for value in ids}) == len(ids)


def test_no_empty_values_outside_optional_columns(data):
    optional = {("employees", "manager_id"), ("support_tickets", "resolved_date")}
    for entity, rows in data.items():
        for row in rows:
            assert set(row) == set(seed_demo.COLUMNS[entity])
            empty = {column for column, value in row.items() if value == ""}
            assert empty <= {column for table, column in optional if table == entity}, (entity, row)
            assert all(value == value.strip() for value in row.values()), (entity, row)


def test_names_titles_and_emails_are_unique_and_synthetic(data):
    for entity, name_column in (("employees", "employee_name"), ("customers", "customer_name"),
                                ("documents", "title")):
        assert len({row[name_column] for row in data[entity]}) == len(data[entity]), entity
    for entity in ("employees", "customers"):
        emails = [row["email_address"] for row in data[entity]]
        assert len(set(emails)) == len(emails)
        assert all(email == email.lower() and email.endswith(".example") for email in emails)
    assert all(row["source_uri"].startswith("https://internal.acme.example/")
               for row in data["documents"])


# ---------------------------------------------------------------------------
# Cross-entity references and business consistency
# ---------------------------------------------------------------------------


def test_every_reference_resolves_to_an_appropriate_record(data, by_id):
    customers = by_id["customers"]
    everyone = _active_staff(data, *{row["title"] for row in data["employees"]})
    assert all(row["organization_id"] == "ORG-001" for row in data["employees"])
    assert {row["account_owner_id"] for row in data["customers"]} == _active_staff(
        data, "Account Executive")
    for row in data["deals"]:
        customer = customers[row["customer_id"]]
        assert customer["status"] == "active"
        assert row["owner_id"] == customer["account_owner_id"]
    assert {row["owner_id"] for row in data["projects"]} == _active_staff(data, *DELIVERY_TITLES)
    assert {row["assignee_id"] for row in data["support_tickets"]} == _active_staff(
        data, "Support Engineer")
    for entity in ("projects", "support_tickets"):
        assert all(customers[row["customer_id"]]["status"] == "active" for row in data[entity])
    assert {row["owner_id"] for row in data["documents"]} <= everyone


def test_management_chain_is_a_tree_rooted_at_the_ceo(data, by_id):
    employees = by_id["employees"]
    roots = [row["employee_id"] for row in data["employees"] if row["manager_id"] == ""]
    assert roots == ["EMP-001"] and employees["EMP-001"]["title"] == "Chief Executive Officer"
    for row in data["employees"]:
        seen, current = set(), row
        while current["manager_id"]:
            assert current["employee_id"] not in seen
            seen.add(current["employee_id"])
            manager = employees[current["manager_id"]]
            assert _day(manager["hire_date"]) < _day(current["hire_date"])
            current = manager
        assert current["employee_id"] == "EMP-001"


def test_employee_status_matches_active_flag(data):
    pairs = {(row["status"], row["is_active"]) for row in data["employees"]}
    assert pairs == {("active", "true"), ("inactive", "false")}
    assert all(_day(row["hire_date"]) <= AS_OF for row in data["employees"])


def test_customer_statuses_and_dates(data):
    statuses = [row["status"] for row in data["customers"]]
    assert statuses.count("inactive") == 4 and statuses.count("active") == 46
    assert {row["customer_segment"] for row in data["customers"]} == {
        "Enterprise", "Mid-Market", "SMB"}
    assert all(_day(row["created_date"]) < AS_OF for row in data["customers"])


def test_deal_stage_consistency(data, by_id):
    assert {row["stage"] for row in data["deals"]} == {"qualification", "negotiation", "won"}
    assert {row["currency"] for row in data["deals"]} == {"INR", "USD", "EUR"}
    for row in data["deals"]:
        close = _day(row["expected_close_date"])
        probability = Decimal(row["probability"])
        if row["stage"] == "won":
            assert (probability, row["is_active"]) == (Decimal(100), "false")
            assert _day(by_id["customers"][row["customer_id"]]["created_date"]) < close < AS_OF
        else:
            assert Decimal(0) < probability < Decimal(100) and row["is_active"] == "true"
            assert close > AS_OF
        if row["stage"] == "qualification":
            assert probability <= 40
        if row["stage"] == "negotiation":
            assert probability >= 50


def test_deal_values_match_the_customer_segment_in_rupees(data, by_id):
    for row in data["deals"]:
        assert row["amount"] == f"{Decimal(row['amount']):.2f}"
        low, high = seed_demo.VALUE_RUPEES[by_id["customers"][row["customer_id"]]["customer_segment"]]
        # Converted amounts are truncated to whole cents.
        assert low - 1 <= _rupees(row) <= high, row


def test_project_consistency(data):
    won_closes = defaultdict(list)
    for row in data["deals"]:
        if row["stage"] == "won":
            won_closes[row["customer_id"]].append(_day(row["expected_close_date"]))
    assert {row["status"] for row in data["projects"]} == {"planning", "in_progress"}
    for row in data["projects"]:
        start, end = _day(row["start_date"]), _day(row["end_date"])
        assert start < end and row["is_active"] == "true"
        assert row["status"] == ("in_progress" if start <= AS_OF else "planning")
        assert Decimal(row["budget"]) > 0
        if row["status"] == "in_progress":
            assert any(close < start for close in won_closes[row["customer_id"]]), row


def test_ticket_lifecycle_consistency(data, by_id):
    tickets = data["support_tickets"]
    assert {row["priority"] for row in tickets} == {"medium", "high"}
    assert {row["status"] for row in tickets} == {"open", "resolved"}
    assert [row["created_date"] for row in tickets] == sorted(row["created_date"] for row in tickets)
    for row in tickets:
        created = _day(row["created_date"])
        assert _day(by_id["customers"][row["customer_id"]]["created_date"]) < created < AS_OF
        if row["status"] == "resolved":
            assert created < _day(row["resolved_date"]) < AS_OF
        else:
            assert row["resolved_date"] == ""
        if (AS_OF - created).days <= 10:
            assert row["status"] == "open"


def test_documents_carry_text_and_ordered_dates(data):
    documents = data["documents"]
    assert len({row["document_type"] for row in documents}) >= 5
    for row in documents:
        assert len(row["body_text"]) >= 150 and "\n" in row["body_text"]
        assert _day(row["created_date"]) <= _day(row["updated_date"]) <= AS_OF


# ---------------------------------------------------------------------------
# Scenarios preserved for later layers
# ---------------------------------------------------------------------------


def _tickets_by_customer(data) -> dict[str, list[dict[str, str]]]:
    grouped = defaultdict(list)
    for row in data["support_tickets"]:
        grouped[row["customer_id"]].append(row)
    return grouped


def test_churn_risk_customer_has_a_ticket_burst_and_an_active_deal(data):
    """Spec Section 12: multiple tickets in a short period plus an active deal."""
    active_deal_customers = {row["customer_id"] for row in data["deals"]
                             if row["is_active"] == "true"}
    at_risk = []
    for customer_id, tickets in _tickets_by_customer(data).items():
        days = sorted(_day(row["created_date"]) for row in tickets)
        burst = any(later - first <= timedelta(days=14)
                    for first, later in zip(days, days[4:], strict=False))
        if burst and customer_id in active_deal_customers:
            at_risk.append(customer_id)
    assert at_risk == [seed_demo.CHURN_RISK_CUSTOMER]
    burst = _tickets_by_customer(data)[seed_demo.CHURN_RISK_CUSTOMER]
    assert sum(row["status"] == "open" for row in burst) == 4
    assert sum(row["priority"] == "high" for row in burst) == 4


def test_selected_customers_have_repeated_tickets(data):
    counts = {customer: len(rows) for customer, rows in _tickets_by_customer(data).items()}
    for customer_id in seed_demo.REPEAT_TICKET_CUSTOMERS:
        assert counts[customer_id] == 4
    assert sum(count >= 3 for count in counts.values()) >= 4


def _document(data, title_prefix: str) -> str:
    return next(row["body_text"] for row in data["documents"]
                if row["title"].startswith(title_prefix))


def test_reports_state_facts_that_match_the_records(data, by_id):
    deals = data["deals"]
    report = _document(data, "Sales Pipeline Report")
    stages = [row["stage"] for row in deals]
    assert (f"qualification {stages.count('qualification')}, negotiation "
            f"{stages.count('negotiation')}, won {stages.count('won')}") in report
    open_inr = sum((Decimal(row["amount"]) for row in deals
                    if row["is_active"] == "true" and row["currency"] == "INR"), Decimal(0))
    assert f"INR {open_inr:,.2f}." in report
    largest = max((row for row in deals if row["stage"] == "negotiation"), key=_rupees)
    assert f"Largest open negotiation: {largest['deal_name']} ({largest['deal_id']})." in report

    trends = _document(data, "Support Ticket Trends")
    august = [row for row in data["support_tickets"] if row["created_date"].startswith("2026-08")]
    assert f"Tickets created: {len(august)}." in trends
    burst = _tickets_by_customer(data)[seed_demo.CHURN_RISK_CUSTOMER]
    churn_name = by_id["customers"][seed_demo.CHURN_RISK_CUSTOMER]["customer_name"]
    assert (f"{churn_name} ({seed_demo.CHURN_RISK_CUSTOMER}) raised {len(burst)} tickets") in trends
    assert f"{sum(row['status'] == 'open' for row in burst)} remain open" in trends


def test_contracts_and_notes_reference_existing_records(data, by_id):
    documents = data["documents"]
    contracts = [row for row in documents if row["document_type"] == "contract"]
    assert len(contracts) == 2
    for row in contracts:
        customer_id = row["body_text"].split("(", 1)[1].split(")", 1)[0]
        assert by_id["customers"][customer_id]["account_owner_id"] == row["owner_id"]
    assert any(seed_demo.CHURN_RISK_CUSTOMER in row["body_text"] for row in contracts)
    assert {row["document_type"] for row in documents} >= {
        "policy", "report", "contract", "proposal", "meeting_notes", "runbook"}


# ---------------------------------------------------------------------------
# Pipeline compatibility and hygiene
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entity", ENTITIES)
def test_dataset_is_clean_in_every_source_representation(generated_dir, data, entity):
    odoo, rest = mock_source.load_source_data(generated_dir)
    payloads = {"csv_demo": data[entity], "odoo_mock": odoo[entity], "rest_mock": rest[entity]}
    for source in SOURCES:
        result = validate_source_batch(source, entity, payloads[source], RUN_ID, INGESTED_AT)
        assert result.quarantined == () and result.warnings == (), source
        assert result.valid_count == len(data[entity])


def test_no_value_resembles_a_credential(data, bad):
    patterns = default_validation_config().quarantine.sensitive_value_patterns
    for dataset in (data, bad):
        for rows in dataset.values():
            for row in rows:
                for value in row.values():
                    assert not any(pattern.search(value) for pattern in patterns), value


# ---------------------------------------------------------------------------
# Bad fixture (spec Section 12 deliberate quality issues)
# ---------------------------------------------------------------------------


def test_bad_fixture_has_every_entity_file_and_passes_the_health_check(cli_root, bad):
    assert _connector(cli_root / "bad").health_check().healthy
    assert {entity: len(rows) for entity, rows in bad.items()} == {
        "organizations": 0, "employees": 0, "customers": 4, "deals": 4, "projects": 0,
        "support_tickets": 0, "documents": 0}


def test_bad_fixture_identities_never_collide_with_the_demo(cli_root, bad):
    demo = _read(cli_root / "demo")
    for entity in ENTITIES:
        assert not _ids(bad[entity]) & _ids(demo[entity]), entity
    assert "CUST-999" not in _ids(demo["customers"]) | _ids(bad["customers"])


def test_bad_fixture_customers_carry_their_quality_issues(bad):
    rows = bad["customers"]
    result = validate_source_batch("csv_demo", "customers", rows, RUN_ID, INGESTED_AT)
    assert [record.source_id for record in result.valid] == ["CUST-901", "CUST-902", "CUST-901"]
    assert [(q.source_id, q.code, q.field_name) for q in result.quarantined] == [
        ("CUST-903", "UNKNOWN_ENUM_VALUE", "status")]
    assert [(rows[w.record_index]["customer_id"], w.code, w.field_name) for w in result.warnings] == [
        ("CUST-902", "MISSING_RECOMMENDED_FIELD", "email"),
        ("CUST-901", "DUPLICATE_SOURCE_RECORD", "source_id")]
    assert rows[3] == rows[0]


def test_bad_fixture_deals_carry_their_quality_issues(bad):
    rows = bad["deals"]
    result = validate_source_batch("csv_demo", "deals", rows, RUN_ID, INGESTED_AT)
    assert [record.source_id for record in result.valid] == ["DEAL-901", "DEAL-902"]
    assert [(q.source_id, q.code, q.field_name) for q in result.quarantined] == [
        ("DEAL-903", "INVALID_DECIMAL", "amount"),
        ("DEAL-904", "INVALID_DATE", "expected_close_date")]
    assert result.warnings == ()
    # D2 accepts the unknown reference; E1 resolves it to NULL with a warning.
    fixture_customers = _ids(bad["customers"])
    assert [(record.source_id, record.customer_source_id) for record in result.valid
            if record.customer_source_id not in fixture_customers] == [("DEAL-902", "CUST-999")]
