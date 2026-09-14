"""
Generate the deterministic Layer 1 demo dataset (make seed).

    python scripts/seed_demo.py
    python scripts/seed_demo.py --check

Writes the csv_demo source files read by the C2 CSV connector and served by
the C3 mock source to data/demo/. Every value derives from SEED and the fixed
snapshot date AS_OF, never from the clock or the environment, so every run
writes byte-identical files; the committed files are this script's output.
--check regenerates the files in memory and reports stale ones without writing.

The dataset follows spec Section 12: one organization, at least 20 employees,
50 customers, 40 deals, 20 projects, 75 support tickets and 10 documents, with
cross-entity references that resolve inside the dataset, repeated tickets for
selected customers, and a churn-risk scenario (a customer with several recent
tickets and an active deal). Values stay inside the canonical vocabulary of
config/mappings/normalization.yaml, so every record normalizes and validates
identically through the csv_demo, odoo_mock and rest_mock representations.

This script never touches the database: ingestion (make ingest-demo) is the
only path into PostgreSQL.

Exit status: 0 files written or up to date, 1 --check found stale files.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = PROJECT_ROOT / "data" / "demo"

SEED = 1101
# Snapshot date of the synthetic enterprise: nothing is created after it,
# open deals close after it and resolved tickets were resolved before it.
AS_OF = date(2026, 9, 1)

Row = dict[str, str]
Dataset = dict[str, list[Row]]

# Column order of each file; the C2 csv_demo mapping reads these names.
COLUMNS: dict[str, tuple[str, ...]] = {
    "organizations": ("organization_id", "organization_name", "industry", "country", "status"),
    "employees": ("employee_id", "employee_name", "email_address", "department", "title",
                  "manager_id", "status", "hire_date", "is_active", "organization_id"),
    "customers": ("customer_id", "customer_name", "email_address", "customer_segment",
                  "industry_name", "account_owner_id", "status", "created_date"),
    "deals": ("deal_id", "deal_name", "customer_id", "owner_id", "stage", "amount", "currency",
              "probability", "expected_close_date", "is_active"),
    "projects": ("project_id", "project_name", "customer_id", "owner_id", "status", "start_date",
                 "end_date", "budget", "is_active"),
    "support_tickets": ("ticket_id", "customer_id", "assignee_id", "priority", "status",
                        "category", "subject", "description", "created_date", "resolved_date"),
    "documents": ("document_id", "title", "document_type", "body_text", "source_uri", "owner_id",
                  "created_date", "updated_date"),
}

# ---------------------------------------------------------------------------
# Organization and employees
# ---------------------------------------------------------------------------

ORGANIZATION_ID = "ORG-001"
ORGANIZATION: Row = {
    "organization_id": ORGANIZATION_ID, "organization_name": "Acme Corp",
    "industry": "Technology", "country": "India", "status": "active",
}
FOUNDED = date(2019, 4, 1)
LATEST_HIRE = AS_OF - timedelta(days=60)

# (department, title, manager's employee number). Row n is EMP-00n.
ROSTER: tuple[tuple[str, str, int | None], ...] = (
    ("Executive", "Chief Executive Officer", None),
    ("Sales", "VP Sales", 1),
    ("Engineering", "VP Engineering", 1),
    ("Customer Support", "Head of Customer Support", 1),
    ("Finance", "Finance Director", 1),
    ("Human Resources", "HR Manager", 1),
    *[("Sales", "Account Executive", 2)] * 5,
    *[("Engineering", "Delivery Lead", 3)] * 2,
    *[("Engineering", "Senior Engineer", 3)] * 2,
    ("Engineering", "Data Engineer", 3),
    *[("Customer Support", "Support Engineer", 4)] * 5,
    ("Finance", "Financial Analyst", 5),
    ("Human Resources", "Talent Partner", 6),
    ("Operations", "Operations Manager", 1),
)
# A former account executive: exercises inactive status in every representation.
INACTIVE_EMPLOYEES = frozenset({"EMP-011"})
DELIVERY_TITLES = frozenset({"Delivery Lead", "Senior Engineer", "Data Engineer"})

FIRST_NAMES = (
    "Aarav", "Priya", "Rohan", "Ananya", "Vikram", "Meera", "Karan", "Divya", "Arjun", "Sneha",
    "Rahul", "Kavya", "Nikhil", "Isha", "Sanjay", "Pooja", "Aditya", "Neha", "Farhan",
    "Lakshmi", "Daniel", "Sofia", "Kenji", "Amara", "Tomas", "Leila",
)
LAST_NAMES = (
    "Sharma", "Iyer", "Patel", "Reddy", "Menon", "Kulkarni", "Joshi", "Nair", "Gupta", "Rao",
    "Desai", "Kapoor", "Bose", "Pillai", "Chatterjee", "Mehta", "Verma", "Sinha", "Bhat", "Khan",
    "Fernandes", "Mathur", "Saxena", "Ghosh", "Dutta", "Agarwal",
)

# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

CUSTOMER_COUNT = 50
SEGMENTS = ("Enterprise",) * 12 + ("Mid-Market",) * 18 + ("SMB",) * 20
INACTIVE_CUSTOMER_COUNT = 4
CUSTOMERS_FROM = date(2023, 1, 2)
CUSTOMERS_UNTIL = date(2026, 3, 31)

# Churn-risk scenario (spec Section 12): several tickets in a short period
# while an active deal is in negotiation. Layer 1 only preserves the facts.
CHURN_RISK_CUSTOMER = "CUST-007"
# Customers with repeated tickets spread over several months.
REPEAT_TICKET_CUSTOMERS = ("CUST-004", "CUST-015", "CUST-028")

COMPANY_PREFIXES = (
    "Aurora", "Bluepeak", "Cedarline", "Deltaforge", "Evergrid", "Falconridge", "Greenmark",
    "Harborview", "Ironwood", "Juniper", "Keystone", "Lumina", "Meridian", "Northstar", "Oakridge",
    "Quantix", "Redwood", "Silverline", "Trident", "Unity", "Vertex", "Westbrook", "Yellowfin",
    "Zenith",
)
# (company name suffix, industry)
COMPANY_TYPES = (
    ("Logistics", "Logistics"), ("Health", "Healthcare"), ("Retail", "Retail"),
    ("Foods", "Food and Beverage"), ("Motors", "Automotive"), ("Energy", "Energy"),
    ("Textiles", "Manufacturing"), ("Pharma", "Healthcare"), ("Finserv", "Financial Services"),
    ("Telecom", "Telecommunications"), ("Analytics", "Technology"), ("Builders", "Construction"),
)

# ---------------------------------------------------------------------------
# Deals and projects
# ---------------------------------------------------------------------------

# One scenario deal plus these, in shuffled order.
DEAL_STAGES = ("won",) * 14 + ("negotiation",) * 13 + ("qualification",) * 16
STAGE_PROBABILITIES = {
    "qualification": (10, 20, 25, 30, 40),
    "negotiation": (50, 60, 70, 75, 80, 90),
    "won": (100,),
}
DEAL_CURRENCIES = ("INR",) * 7 + ("USD",) * 2 + ("EUR",)
# Fixed synthetic conversion rates: deal values are drawn in rupees.
RUPEES_PER_UNIT = {"INR": 1, "USD": 83, "EUR": 90}
VALUE_RUPEES = {
    "Enterprise": (2_000_000, 15_000_000),
    "Mid-Market": (500_000, 2_500_000),
    "SMB": (50_000, 600_000),
}
DEAL_PRODUCTS = (
    "Platform Subscription", "Analytics Suite", "Support Renewal", "Data Migration",
    "Integration Services", "Seat Expansion", "Reporting Add-on",
)
# Projects start from every won deal plus this many negotiations in planning.
PLANNED_PROJECT_COUNT = 8
PROJECT_TEMPLATES = (
    "Platform Rollout", "CRM Integration", "Data Warehouse Build", "Support Portal Launch",
    "Analytics Onboarding",
)

# ---------------------------------------------------------------------------
# Support tickets
# ---------------------------------------------------------------------------

TICKET_COUNT = 80
TICKET_WINDOW_DAYS = 240
# Tickets raised within this many days of AS_OF are still open.
OPEN_TICKET_DAYS = 10
REPEAT_TICKETS_PER_CUSTOMER = 4
PRIORITIES = ("medium", "medium", "medium", "high")

# (days before AS_OF, category, priority, days to resolve or None, subject, description)
CHURN_RISK_TICKETS = (
    (14, "performance", "high", 2, "Dashboards take over 30 seconds to load",
     "Executive dashboards time out during the morning review; the delay started after the "
     "last release."),
    (12, "performance", "high", None, "Nightly data sync times out",
     "The nightly sync job has failed three nights in a row with timeout errors, leaving "
     "reports a day stale."),
    (9, "integration", "high", None, "Webhook deliveries failing after upgrade",
     "Order webhooks return HTTP 500 since the platform upgrade, so the customer's ERP is "
     "missing updates."),
    (7, "billing", "medium", None, "Invoice includes removed licences",
     "The August invoice charges for 40 seats although 12 seats were removed in July."),
    (5, "performance", "high", None, "Month-end close blocked by slow exports",
     "Finance exports take several hours and block the month-end close; the customer has "
     "asked for an escalation call."),
)

TICKET_TOPICS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("auth", (
        ("Single sign-on login loop",
         "Users are sent back to the login page after authenticating with the identity provider."),
        ("Two-factor codes rejected",
         "Several users report that valid two-factor codes are rejected on the first attempt."),
        ("New users cannot sign in",
         "Accounts created this week receive an access denied message on first sign-in."),
    )),
    ("billing", (
        ("Invoice total does not match contract",
         "The latest invoice total differs from the amount agreed in the order form."),
        ("Duplicate charge on monthly invoice",
         "The monthly subscription appears twice on the most recent invoice."),
        ("Revised tax invoice requested",
         "The customer needs the invoice reissued with the updated registered address."),
    )),
    ("performance", (
        ("Slow report generation",
         "Scheduled reports take more than ten minutes to generate during business hours."),
        ("Search results load slowly",
         "Searching customer records takes several seconds for large accounts."),
        ("Mobile app lag on dashboards",
         "Dashboard widgets load slowly on the mobile app over cellular networks."),
    )),
    ("integration", (
        ("CRM sync missing contacts",
         "Contacts created in the CRM do not appear after the scheduled sync."),
        ("API rate limit errors",
         "Batch jobs receive HTTP 429 responses during the nightly import window."),
        ("Accounting export rejected",
         "The accounting system rejects the export file because of a column mismatch."),
    )),
    ("data", (
        ("Duplicate records after import",
         "The bulk import created duplicate records for accounts that already existed."),
        ("Report totals differ from source",
         "Monthly revenue totals in the report differ from the finance system."),
        ("Scheduled export missing rows",
         "The weekly export omits records updated on the last day of the week."),
    )),
    ("onboarding", (
        ("Admin training session request",
         "The customer requests a training session for newly appointed administrators."),
        ("Help configuring user roles",
         "The customer needs guidance on mapping team responsibilities to user roles."),
        ("Bulk user import template",
         "The customer asks for the template and steps to import users in bulk."),
    )),
)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _id(prefix: str, number: int) -> str:
    return f"{prefix}-{number:03d}"


def _day(value: str) -> date:
    return date.fromisoformat(value)


def _between(rng: random.Random, start: date, end: date) -> date:
    """A date in [start, end]."""
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _rupees(rng: random.Random, segment: str) -> int:
    low, high = VALUE_RUPEES[segment]
    return rng.randint(low // 500, high // 500) * 500


def _money(minor_units: int) -> str:
    return f"{minor_units // 100}.{minor_units % 100:02d}"


def _employees(rng: random.Random) -> list[Row]:
    firsts = rng.sample(FIRST_NAMES, len(ROSTER))
    lasts = rng.sample(LAST_NAMES, len(ROSTER))
    hired: dict[str, date] = {}
    rows = []
    for number, ((department, title, manager), first, last) in enumerate(
            zip(ROSTER, firsts, lasts, strict=True), 1):
        employee_id = _id("EMP", number)
        if manager is None:
            manager_id, hire = "", FOUNDED
        else:
            manager_id = _id("EMP", manager)
            boss_hired = hired[manager_id]
            hire = boss_hired + timedelta(days=rng.randint(30, (LATEST_HIRE - boss_hired).days // 2))
        hired[employee_id] = hire
        active = employee_id not in INACTIVE_EMPLOYEES
        rows.append({
            "employee_id": employee_id,
            "employee_name": f"{first} {last}",
            "email_address": f"{first}.{last}@acme.example".lower(),
            "department": department,
            "title": title,
            "manager_id": manager_id,
            "status": "active" if active else "inactive",
            "hire_date": hire.isoformat(),
            "is_active": "true" if active else "false",
            "organization_id": ORGANIZATION_ID,
        })
    return rows


def _active_ids(employees: list[Row], titles: frozenset[str]) -> list[str]:
    return [row["employee_id"] for row in employees
            if row["title"] in titles and row["is_active"] == "true"]


def _customers(rng: random.Random, account_executives: list[str]) -> list[Row]:
    names = rng.sample([(prefix, kind) for prefix in COMPANY_PREFIXES for kind in COMPANY_TYPES],
                       CUSTOMER_COUNT)
    segments = list(SEGMENTS)
    rng.shuffle(segments)
    rows = []
    for number, ((prefix, (suffix, industry)), segment) in enumerate(
            zip(names, segments, strict=True), 1):
        customer_id = _id("CUST", number)
        rows.append({
            "customer_id": customer_id,
            "customer_name": f"{prefix} {suffix}",
            "email_address": f"contact@{prefix}-{suffix}.example".lower(),
            "customer_segment": segment,
            "industry_name": industry,
            "account_owner_id": rng.choice(account_executives),
            "status": "active",
            "created_date": _between(rng, CUSTOMERS_FROM, CUSTOMERS_UNTIL).isoformat(),
        })
    scenario = {CHURN_RISK_CUSTOMER, *REPEAT_TICKET_CUSTOMERS}
    for row in rng.sample([row for row in rows if row["customer_id"] not in scenario],
                          INACTIVE_CUSTOMER_COUNT):
        row["status"] = "inactive"
    return rows


def _deals(rng: random.Random, customers: list[Row]) -> list[Row]:
    """Deals belong to active customers and are owned by the account owner."""
    active = [row for row in customers if row["status"] == "active"]
    stages = list(DEAL_STAGES)
    rng.shuffle(stages)
    churn_risk = next(row for row in active if row["customer_id"] == CHURN_RISK_CUSTOMER)
    plan = [(churn_risk, "negotiation")] + [(rng.choice(active), stage) for stage in stages]
    rows = []
    for number, (customer, stage) in enumerate(plan, 1):
        currency = rng.choice(DEAL_CURRENCIES)
        if stage == "won":
            close = _between(rng, _day(customer["created_date"]) + timedelta(days=30),
                             AS_OF - timedelta(days=15))
        else:
            close = AS_OF + timedelta(days=rng.randint(14, 240))
        amount = _rupees(rng, customer["customer_segment"]) * 100 // RUPEES_PER_UNIT[currency]
        rows.append({
            "deal_id": _id("DEAL", number),
            "deal_name": f"{customer['customer_name']} - {rng.choice(DEAL_PRODUCTS)}",
            "customer_id": customer["customer_id"],
            "owner_id": customer["account_owner_id"],
            "stage": stage,
            "amount": _money(amount),
            "currency": currency,
            "probability": f"{rng.choice(STAGE_PROBABILITIES[stage])}.00",
            "expected_close_date": close.isoformat(),
            "is_active": "false" if stage == "won" else "true",
        })
    return rows


def _projects(rng: random.Random, customers: list[Row], deals: list[Row],
              delivery_owners: list[str]) -> list[Row]:
    """Delivery projects for every won deal plus planned work for some negotiations."""
    by_id = {row["customer_id"]: row for row in customers}
    starts = [(deal, _day(deal["expected_close_date"]) + timedelta(days=rng.randint(7, 30)))
              for deal in deals if deal["stage"] == "won"]
    negotiations = [deal for deal in deals if deal["stage"] == "negotiation"]
    starts += [(deal, AS_OF + timedelta(days=rng.randint(14, 90)))
               for deal in rng.sample(negotiations, PLANNED_PROJECT_COUNT)]
    rows = []
    for number, (deal, start) in enumerate(starts, 1):
        customer = by_id[deal["customer_id"]]
        budget = _rupees(rng, customer["customer_segment"]) * rng.randint(40, 80) // 100
        rows.append({
            "project_id": _id("PROJ", number),
            "project_name": f"{customer['customer_name']} {rng.choice(PROJECT_TEMPLATES)}",
            "customer_id": customer["customer_id"],
            "owner_id": rng.choice(delivery_owners),
            "status": "in_progress" if start <= AS_OF else "planning",
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=rng.randint(90, 365))).isoformat(),
            "budget": f"{budget}.00",
            "is_active": "true",
        })
    return rows


def _ticket(customer_id: str, assignee_id: str, created: date, category: str, priority: str,
            resolve_days: int | None, subject: str, description: str) -> Row:
    return {
        "customer_id": customer_id,
        "assignee_id": assignee_id,
        "priority": priority,
        "status": "open" if resolve_days is None else "resolved",
        "category": category,
        "subject": subject,
        "description": description,
        "created_date": created.isoformat(),
        "resolved_date": "" if resolve_days is None else
        (created + timedelta(days=resolve_days)).isoformat(),
    }


def _tickets(rng: random.Random, customers: list[Row], support_engineers: list[str]) -> list[Row]:
    """Tickets from active customers, numbered in creation order."""
    active = {row["customer_id"]: row for row in customers if row["status"] == "active"}

    def window_start(customer_id: str) -> date:
        return max(_day(active[customer_id]["created_date"]) + timedelta(days=7),
                   AS_OF - timedelta(days=TICKET_WINDOW_DAYS))

    def topic() -> tuple[str, str, str]:
        category, choices = rng.choice(TICKET_TOPICS)
        subject, description = rng.choice(choices)
        return category, subject, description

    drafts = [
        _ticket(CHURN_RISK_CUSTOMER, rng.choice(support_engineers),
                AS_OF - timedelta(days=days_before), category, priority, resolve_days, subject,
                description)
        for days_before, category, priority, resolve_days, subject, description
        in CHURN_RISK_TICKETS
    ]
    for customer_id in REPEAT_TICKET_CUSTOMERS:
        start = window_start(customer_id)
        latest = AS_OF - timedelta(days=30)
        for offset in sorted(rng.sample(range((latest - start).days + 1),
                                        REPEAT_TICKETS_PER_CUSTOMER)):
            category, subject, description = topic()
            drafts.append(_ticket(customer_id, rng.choice(support_engineers),
                                  start + timedelta(days=offset), category, rng.choice(PRIORITIES),
                                  rng.randint(1, 9), subject, description))
    scenario = {CHURN_RISK_CUSTOMER, *REPEAT_TICKET_CUSTOMERS}
    pool = [customer_id for customer_id in active if customer_id not in scenario]
    while len(drafts) < TICKET_COUNT:
        customer_id = rng.choice(pool)
        created = _between(rng, window_start(customer_id), AS_OF - timedelta(days=1))
        category, subject, description = topic()
        recent = (AS_OF - created).days <= OPEN_TICKET_DAYS
        # Older tickets are resolved, apart from an occasional backlog item.
        resolve_days = None if recent or rng.randint(1, 8) == 1 else rng.randint(1, 9)
        drafts.append(_ticket(customer_id, rng.choice(support_engineers), created, category,
                              rng.choice(PRIORITIES), resolve_days, subject, description))
    drafts.sort(key=lambda row: (row["created_date"], row["customer_id"], row["subject"]))
    return [{"ticket_id": _id("TKT", number), **row} for number, row in enumerate(drafts, 1)]


def _inr(value: Decimal) -> str:
    return f"INR {value:,.2f}"


def _documents(employees: list[Row], customers: list[Row], deals: list[Row],
               projects: list[Row], tickets: list[Row]) -> list[Row]:
    """Institutional documents whose text states facts from the dataset."""
    people = {row["employee_id"]: row["employee_name"] for row in employees}
    customer = {row["customer_id"]: row for row in customers}
    churn_risk = customer[CHURN_RISK_CUSTOMER]
    churn_deal = next(row for row in deals if row["customer_id"] == CHURN_RISK_CUSTOMER
                      and row["is_active"] == "true")
    churn_tickets = [row for row in tickets if row["customer_id"] == CHURN_RISK_CUSTOMER]
    open_churn_tickets = sum(1 for row in churn_tickets if row["status"] == "open")
    stage_counts = Counter(row["stage"] for row in deals)
    open_inr = sum((Decimal(row["amount"]) for row in deals
                    if row["is_active"] == "true" and row["currency"] == "INR"), Decimal(0))
    august = [row for row in tickets if row["created_date"].startswith("2026-08")]
    august_categories = Counter(row["category"] for row in august)
    # A second contract for a different customer than the churn-risk one.
    won_deal = next(row for row in deals if row["stage"] == "won"
                    and row["customer_id"] != CHURN_RISK_CUSTOMER)
    msa_customer = customer[won_deal["customer_id"]]
    proposal_deal = max((row for row in deals if row["stage"] == "negotiation"),
                        key=lambda row: Decimal(row["amount"]) * RUPEES_PER_UNIT[row["currency"]])
    kickoff = next(row for row in projects if row["status"] == "in_progress")

    def msa(client: Row) -> str:
        return (
            f"Master Services Agreement between Acme Corp and {client['customer_name']} "
            f"({client['customer_id']}).\n\n"
            f"Effective date: {client['created_date']}.\n"
            "Term: 36 months, renewing annually unless either party gives 90 days' written "
            "notice.\n"
            "Service levels: as defined in the Customer Support SLA Policy.\n"
            "Fees: invoiced quarterly in advance; undisputed invoices are payable within 30 days."
        )

    specs = [
        ("Employee Handbook 2026", "policy", "EMP-006", "2026-01-05", "2026-06-15", (
            "Acme Corp Employee Handbook 2026\n\n"
            "1. Working hours: core collaboration hours are 10:00 to 16:00 IST, Monday to Friday.\n"
            "2. Leave: employees accrue 1.75 days of paid leave per month; requests go to the "
            "direct manager.\n"
            "3. Conduct: treat colleagues and customers with respect and report concerns to "
            "Human Resources.\n"
            "4. Equipment: company laptops use full-disk encryption and automatic screen lock.\n"
            "5. Expenses: submit claims with receipts within 30 days."
        )),
        ("Information Security Policy", "policy", "EMP-003", "2025-11-10", "2026-04-02", (
            "Information Security Policy\n\n"
            "Access to customer data is granted on a least-privilege basis and reviewed "
            "quarterly.\n"
            "Credentials are kept in the approved secrets manager and are never shared by email "
            "or chat.\n"
            "Security incidents are reported to Engineering within one hour of discovery.\n"
            "Production changes require peer review and an approved change request."
        )),
        ("Customer Support SLA Policy", "policy", "EMP-004", "2025-09-01", "2026-02-20", (
            "Customer Support SLA Policy\n\n"
            "High priority: first response within 2 business hours; resolution target 1 business "
            "day.\n"
            "Medium priority: first response within 8 business hours; resolution target 5 "
            "business days.\n"
            "Customers raising three or more tickets within 14 days are escalated to their "
            "account owner."
        )),
        (f"Sales Pipeline Report {AS_OF.isoformat()}", "report", "EMP-002", AS_OF.isoformat(),
         AS_OF.isoformat(), (
             f"Sales pipeline as of {AS_OF.isoformat()}\n\n"
             f"Deals by stage: qualification {stage_counts['qualification']}, negotiation "
             f"{stage_counts['negotiation']}, won {stage_counts['won']}.\n"
             f"Open pipeline value of INR-denominated deals: {_inr(open_inr)}.\n"
             f"Largest open negotiation: {proposal_deal['deal_name']} ({proposal_deal['deal_id']})."
         )),
        ("Support Ticket Trends August 2026", "report", "EMP-004", AS_OF.isoformat(),
         AS_OF.isoformat(), (
             "Support ticket trends, August 2026\n\n"
             f"Tickets created: {len(august)}.\n"
             "By category: " + ", ".join(f"{name} {count}" for name, count
                                         in sorted(august_categories.items())) + ".\n"
             f"Escalation: {churn_risk['customer_name']} ({CHURN_RISK_CUSTOMER}) raised "
             f"{len(churn_tickets)} tickets between {churn_tickets[0]['created_date']} and "
             f"{churn_tickets[-1]['created_date']}; {open_churn_tickets} remain open while deal "
             f"{churn_deal['deal_id']} is in {churn_deal['stage']}."
         )),
        (f"Master Services Agreement - {churn_risk['customer_name']}", "contract",
         churn_risk["account_owner_id"], churn_risk["created_date"], churn_risk["created_date"],
         msa(churn_risk)),
        (f"Master Services Agreement - {msa_customer['customer_name']}", "contract",
         msa_customer["account_owner_id"], msa_customer["created_date"],
         won_deal["expected_close_date"], msa(msa_customer)),
        (f"Proposal - {proposal_deal['deal_name']}", "proposal", proposal_deal["owner_id"],
         (AS_OF - timedelta(days=20)).isoformat(), (AS_OF - timedelta(days=6)).isoformat(), (
             f"Commercial proposal for {customer[proposal_deal['customer_id']]['customer_name']} "
             f"({proposal_deal['deal_id']}).\n\n"
             f"Value: {proposal_deal['currency']} {proposal_deal['amount']}.\n"
             f"Expected close date: {proposal_deal['expected_close_date']}.\n"
             "Scope: licences, implementation services and twelve months of standard support."
         )),
        (f"Account Review Notes - {churn_risk['customer_name']}", "meeting_notes",
         churn_risk["account_owner_id"], (AS_OF - timedelta(days=2)).isoformat(),
         (AS_OF - timedelta(days=2)).isoformat(), (
             f"Account review: {churn_risk['customer_name']} ({CHURN_RISK_CUSTOMER})\n\n"
             f"Attendees: {people[churn_risk['account_owner_id']]} (account owner), "
             f"{people['EMP-004']} (Head of Customer Support).\n"
             f"Discussion: {len(churn_tickets)} support tickets in "
             f"{(_day(churn_tickets[-1]['created_date']) - _day(churn_tickets[0]['created_date'])).days}"
             f" days, mostly performance issues. The customer tied the {churn_deal['deal_name']} "
             f"decision ({churn_deal['deal_id']}) to resolving them.\n"
             "Actions: daily status updates until the open tickets are resolved; executive "
             "sponsor call next week."
         )),
        ("Incident Postmortem - Nightly Data Sync Timeouts", "report", "EMP-003",
         (AS_OF - timedelta(days=3)).isoformat(), (AS_OF - timedelta(days=1)).isoformat(), (
             "Incident postmortem: nightly data sync timeouts\n\n"
             "Impact: nightly sync jobs for large accounts timed out, leaving reports stale.\n"
             "Root cause: a query introduced in the latest release scanned full history instead "
             "of the changed window.\n"
             "Remediation: the query was restored to incremental reads and a runtime alert was "
             "added."
         )),
        (f"Project Kickoff Notes - {kickoff['project_name']}", "meeting_notes", kickoff["owner_id"],
         kickoff["start_date"], kickoff["start_date"], (
             f"Kickoff: {kickoff['project_name']} ({kickoff['project_id']})\n\n"
             f"Delivery lead: {people[kickoff['owner_id']]}.\n"
             f"Planned timeline: {kickoff['start_date']} to {kickoff['end_date']}.\n"
             f"Budget: INR {kickoff['budget']}.\n"
             "Next steps: confirm data sources, agree acceptance criteria, schedule weekly "
             "check-ins."
         )),
        ("Customer Onboarding Runbook", "runbook", "EMP-024", "2025-06-12", "2026-05-08", (
            "Customer onboarding runbook\n\n"
            "1. Create the customer workspace and invite the named administrators.\n"
            "2. Import users from the customer's template and assign roles.\n"
            "3. Configure integrations and run a test sync.\n"
            "4. Hold the administrator training session.\n"
            "5. Hand over to Customer Support with the agreed SLA."
        )),
    ]
    return [
        {
            "document_id": _id("DOC", number),
            "title": title,
            "document_type": document_type,
            "body_text": body_text,
            "source_uri": f"https://internal.acme.example/docs/doc-{number:03d}",
            "owner_id": owner_id,
            "created_date": created,
            "updated_date": updated,
        }
        for number, (title, document_type, owner_id, created, updated, body_text)
        in enumerate(specs, 1)
    ]


def build_demo_dataset(seed: int = SEED) -> Dataset:
    """The demo dataset as csv_demo rows per entity, in file order."""
    rng = random.Random(seed)
    employees = _employees(rng)
    customers = _customers(rng, _active_ids(employees, frozenset({"Account Executive"})))
    deals = _deals(rng, customers)
    projects = _projects(rng, customers, deals, _active_ids(employees, DELIVERY_TITLES))
    tickets = _tickets(rng, customers, _active_ids(employees, frozenset({"Support Engineer"})))
    return {
        "organizations": [dict(ORGANIZATION)],
        "employees": employees,
        "customers": customers,
        "deals": deals,
        "projects": projects,
        "support_tickets": tickets,
        "documents": _documents(employees, customers, deals, projects, tickets),
    }


def render_csv(entity: str, rows: Sequence[Row]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS[entity], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def render_dataset(dataset: Dataset) -> dict[str, bytes]:
    """File name -> file content."""
    return {f"{entity}.csv": render_csv(entity, rows) for entity, rows in dataset.items()}


def stale_files(files: dict[str, bytes], directory: Path) -> list[str]:
    """Names of files that are missing from directory or differ from files."""
    return [name for name, content in files.items()
            if not (directory / name).is_file() or (directory / name).read_bytes() != content]


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the deterministic demo dataset.")
    parser.add_argument("--demo-dir", type=Path, default=DEMO_DIR,
                        help="output directory (default: data/demo)")
    parser.add_argument("--check", action="store_true",
                        help="report stale files and exit 1 instead of writing")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    dataset = build_demo_dataset()
    files = render_dataset(dataset)
    if args.check:
        stale = stale_files(files, args.demo_dir)
        if stale:
            print(f"seed_demo: stale files in {args.demo_dir}: {', '.join(stale)}", file=sys.stderr)
            return 1
        print(f"seed_demo: {len(files)} files up to date in {args.demo_dir}")
        return 0
    args.demo_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (args.demo_dir / name).write_bytes(content)
    print(json.dumps({"directory": str(args.demo_dir),
                      "records": {entity: len(rows) for entity, rows in dataset.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
