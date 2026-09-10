"""
Deterministic mock-source HTTP server for Layer 1.

Reads source data from CSV files (the shared demo dataset) and serves
it through /odoo/... and /rest/... endpoints with source-specific
field naming and types.

Architecture:
    data/demo/*.csv (shared source of truth)
          │
          ├──────────► C2 CsvConnector (raw CSV strings)
          │
          └──────────► C3 MockSource (transforms to Odoo/REST JSON)
                            │
                 ┌──────────┴──────────┐
                 ▼                     ▼
            /odoo/...             /rest/...
            (int IDs,             (str IDs,
             Odoo fields)          camelCase)

The CSV-to-Odoo/REST transformation is not normalization. It simulates
what each source system's API would natively return. A real Odoo API
returns typed JSON with integer IDs and Odoo field names. A real REST
API returns camelCase JSON with string IDs. The mock server replicates
those native representations from a shared dataset.

GET-only. POST/PUT/PATCH/DELETE return 405.
"""

import csv
import json
import os
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs


# ---------------------------------------------------------------------------
# CSV-to-source transformation mappings
# ---------------------------------------------------------------------------
# Each entity defines how CSV fields map to Odoo and REST representations.
# This is source-system simulation, not normalization.


def _to_int(val: str) -> int | None:
    """Extract integer from a source ID string like 'CUST-001' -> 1."""
    if not val:
        return None
    digits = re.sub(r"[^0-9]", "", val)
    return int(digits) if digits else None


def _to_float(val: str) -> float | None:
    """Convert numeric string to float for typed JSON sources."""
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _to_bool(val: str) -> bool:
    """Convert string boolean for typed JSON sources."""
    return val.lower() in ("true", "1", "yes", "active") if val else False


def _odoo_datetime(val: str) -> str | None:
    """Format date string as Odoo datetime (YYYY-MM-DD HH:MM:SS)."""
    if not val:
        return None
    if " " in val:
        return val
    return f"{val} 00:00:00"


def _rest_datetime(val: str) -> str | None:
    """Format date string as ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)."""
    if not val:
        return None
    if "T" in val:
        return val
    return f"{val}T00:00:00Z"


# ---------------------------------------------------------------------------
# Per-entity CSV → Odoo/REST transformers
# ---------------------------------------------------------------------------


def _csv_to_odoo_organization(row: dict) -> dict:
    return {
        "id": _to_int(row["organization_id"]),
        "name": row["organization_name"],
        "industry_id": row.get("industry") or None,
        "country_id": row.get("country") or None,
        "active": _to_bool(row.get("status", "")),
    }


def _csv_to_rest_organization(row: dict) -> dict:
    return {
        "id": row["organization_id"],
        "name": row["organization_name"],
        "industry": row.get("industry") or None,
        "country": row.get("country") or None,
        "status": row.get("status") or None,
    }


def _csv_to_odoo_employee(row: dict) -> dict:
    return {
        "id": _to_int(row["employee_id"]),
        "name": row["employee_name"],
        "work_email": row.get("email_address") or None,
        "department_id": row.get("department") or None,
        "job_title": row.get("title") or None,
        "parent_id": _to_int(row.get("manager_id", "")),
        "active": _to_bool(row.get("is_active", "")),
        "x_hire_date": row.get("hire_date") or None,
        "company_id": _to_int(row.get("organization_id", "")),
    }


def _csv_to_rest_employee(row: dict) -> dict:
    return {
        "id": row["employee_id"],
        "name": row["employee_name"],
        "email": row.get("email_address") or None,
        "department": row.get("department") or None,
        "title": row.get("title") or None,
        "managerId": row.get("manager_id") or None,
        "status": row.get("status") or None,
        "hireDate": row.get("hire_date") or None,
        "isActive": _to_bool(row.get("is_active", "")),
        "organizationId": row.get("organization_id") or None,
    }


def _csv_to_odoo_customer(row: dict) -> dict:
    return {
        "id": _to_int(row["customer_id"]),
        "name": row["customer_name"],
        "email": row.get("email_address") or None,
        "x_studio_segment": row.get("customer_segment") or None,
        "industry_id": row.get("industry_name") or None,
        "user_id": _to_int(row.get("account_owner_id", "")),
        "active": _to_bool(row.get("status", "")),
        "create_date": _odoo_datetime(row.get("created_date", "")),
        "customer_rank": 1,
    }


def _csv_to_rest_customer(row: dict) -> dict:
    return {
        "id": row["customer_id"],
        "name": row["customer_name"],
        "email": row.get("email_address") or None,
        "segment": row.get("customer_segment") or None,
        "industry": row.get("industry_name") or None,
        "ownerId": row.get("account_owner_id") or None,
        "status": row.get("status") or None,
        "createdAt": _rest_datetime(row.get("created_date", "")),
        "isActive": _to_bool(row.get("status", "")),
    }


def _csv_to_odoo_deal(row: dict) -> dict:
    return {
        "id": _to_int(row["deal_id"]),
        "name": row["deal_name"],
        "partner_id": _to_int(row.get("customer_id", "")),
        "user_id": _to_int(row.get("owner_id", "")),
        "stage_id": row.get("stage") or None,
        "expected_revenue": _to_float(row.get("amount", "")),
        "company_currency": row.get("currency") or None,
        "probability": _to_float(row.get("probability", "")),
        "date_deadline": row.get("expected_close_date") or None,
        "active": _to_bool(row.get("is_active", "")),
    }


def _csv_to_rest_deal(row: dict) -> dict:
    return {
        "id": row["deal_id"],
        "name": row["deal_name"],
        "customerId": row.get("customer_id") or None,
        "ownerId": row.get("owner_id") or None,
        "stage": row.get("stage") or None,
        "amount": _to_float(row.get("amount", "")),
        "currency": row.get("currency") or None,
        "probability": _to_float(row.get("probability", "")),
        "expectedCloseDate": row.get("expected_close_date") or None,
        "isActive": _to_bool(row.get("is_active", "")),
    }


def _csv_to_odoo_project(row: dict) -> dict:
    return {
        "id": _to_int(row["project_id"]),
        "name": row["project_name"],
        "partner_id": _to_int(row.get("customer_id", "")),
        "user_id": _to_int(row.get("owner_id", "")),
        "stage_id": row.get("status") or None,
        "date_start": row.get("start_date") or None,
        "date": row.get("end_date") or None,
        "x_budget": _to_float(row.get("budget", "")),
        "active": _to_bool(row.get("is_active", "")),
    }


def _csv_to_rest_project(row: dict) -> dict:
    return {
        "id": row["project_id"],
        "name": row["project_name"],
        "customerId": row.get("customer_id") or None,
        "ownerId": row.get("owner_id") or None,
        "status": row.get("status") or None,
        "startDate": row.get("start_date") or None,
        "endDate": row.get("end_date") or None,
        "budget": _to_float(row.get("budget", "")),
        "isActive": _to_bool(row.get("is_active", "")),
    }


def _csv_to_odoo_support_ticket(row: dict) -> dict:
    return {
        "id": _to_int(row["ticket_id"]),
        "partner_id": _to_int(row.get("customer_id", "")),
        "user_id": _to_int(row.get("assignee_id", "")),
        "priority": row.get("priority") or None,
        "stage_id": row.get("status") or None,
        "category_id": row.get("category") or None,
        "name": row.get("subject") or None,
        "description": row.get("description") or None,
        "create_date": _odoo_datetime(row.get("created_date", "")),
        "close_date": _odoo_datetime(row.get("resolved_date", "")),
    }


def _csv_to_rest_support_ticket(row: dict) -> dict:
    return {
        "id": row["ticket_id"],
        "customerId": row.get("customer_id") or None,
        "assigneeId": row.get("assignee_id") or None,
        "priority": row.get("priority") or None,
        "status": row.get("status") or None,
        "category": row.get("category") or None,
        "subject": row.get("subject") or None,
        "description": row.get("description") or None,
        "createdAt": _rest_datetime(row.get("created_date", "")),
        "resolvedAt": _rest_datetime(row.get("resolved_date", "")),
    }


def _csv_to_odoo_document(row: dict) -> dict:
    return {
        "id": _to_int(row["document_id"]),
        "name": row.get("title") or None,
        "type": row.get("document_type") or None,
        "datas": row.get("body_text") or None,
        "url": row.get("source_uri") or None,
        "owner_id": _to_int(row.get("owner_id", "")),
        "create_date": _odoo_datetime(row.get("created_date", "")),
        "write_date": _odoo_datetime(row.get("updated_date", "")),
    }


def _csv_to_rest_document(row: dict) -> dict:
    return {
        "id": row["document_id"],
        "title": row.get("title") or None,
        "documentType": row.get("document_type") or None,
        "bodyText": row.get("body_text") or None,
        "sourceUri": row.get("source_uri") or None,
        "ownerId": row.get("owner_id") or None,
        "createdAt": _rest_datetime(row.get("created_date", "")),
        "updatedAt": _rest_datetime(row.get("updated_date", "")),
    }


# Mapping: entity_type -> (csv_filename, odoo_transformer, rest_transformer)
ENTITY_CONFIG = {
    "organizations": ("organizations.csv", _csv_to_odoo_organization, _csv_to_rest_organization),
    "employees": ("employees.csv", _csv_to_odoo_employee, _csv_to_rest_employee),
    "customers": ("customers.csv", _csv_to_odoo_customer, _csv_to_rest_customer),
    "deals": ("deals.csv", _csv_to_odoo_deal, _csv_to_rest_deal),
    "projects": ("projects.csv", _csv_to_odoo_project, _csv_to_rest_project),
    "support_tickets": ("support_tickets.csv", _csv_to_odoo_support_ticket, _csv_to_rest_support_ticket),
    "documents": ("documents.csv", _csv_to_odoo_document, _csv_to_rest_document),
}

VALID_ENTITIES = set(ENTITY_CONFIG.keys())


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_source_data(data_dir: str | Path) -> tuple[dict, dict]:
    """Load CSV files from data_dir and transform into Odoo/REST dicts.

    Returns (odoo_data, rest_data) where each is a dict mapping
    entity_type to list of source-native records.
    """
    data_path = Path(data_dir)
    odoo_data: dict[str, list[dict]] = {}
    rest_data: dict[str, list[dict]] = {}

    for entity_type, (filename, odoo_fn, rest_fn) in ENTITY_CONFIG.items():
        csv_path = data_path / filename
        if not csv_path.exists():
            print(f"[mock-source] WARNING: {csv_path} not found, {entity_type} will be empty")
            odoo_data[entity_type] = []
            rest_data[entity_type] = []
            continue

        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        odoo_data[entity_type] = [odoo_fn(row) for row in rows]
        rest_data[entity_type] = [rest_fn(row) for row in rows]

        print(f"[mock-source] Loaded {len(rows)} {entity_type} from {filename}")

    return odoo_data, rest_data


# Module-level data stores, populated by load_source_data()
ODOO_DATA: dict[str, list[dict]] = {}
REST_DATA: dict[str, list[dict]] = {}


# ---------------------------------------------------------------------------
# Route patterns
# ---------------------------------------------------------------------------

_ENTITY_LIST_RE = re.compile(r"^/(odoo|rest)/([a-z_]+)$")
_ENTITY_DETAIL_RE = re.compile(r"^/(odoo|rest)/([a-z_]+)/(.+)$")


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------


class MockSourceHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for the mock-source service."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json(200, {
                "status": "healthy",
                "service": "mock-source",
                "entities": sorted(VALID_ENTITIES),
                "routes": ["/health", "/odoo/{entity}", "/rest/{entity}"],
            })
            return

        if path == "":
            self._send_json(200, {
                "service": "mock-source",
                "paths": {
                    "/health": "Service health check",
                    "/odoo/{entity}": "Odoo-style source endpoints",
                    "/rest/{entity}": "Generic REST source endpoints",
                },
            })
            return

        # Entity detail: /odoo/<entity>/<id> or /rest/<entity>/<id>
        match = _ENTITY_DETAIL_RE.match(path)
        if match:
            source_type = match.group(1)
            entity_type = match.group(2)
            record_id = match.group(3)
            self._handle_entity_detail(source_type, entity_type, record_id)
            return

        # Entity list: /odoo/<entity> or /rest/<entity>
        match = _ENTITY_LIST_RE.match(path)
        if match:
            source_type = match.group(1)
            entity_type = match.group(2)
            self._handle_entity_list(source_type, entity_type, query)
            return

        self._send_json(404, {
            "error": "not_found",
            "message": f"Route not found: {self.path}",
        })

    def do_POST(self) -> None:
        self._method_not_allowed()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        """Return 405 for non-GET methods."""
        self._send_json(405, {
            "error": "method_not_allowed",
            "message": f"Method {self.command} is not allowed. This service is read-only (GET only).",
        })

    def _handle_entity_list(
        self, source_type: str, entity_type: str, query: dict
    ) -> None:
        """Handle GET /odoo/<entity> or /rest/<entity> with pagination."""
        data_store = ODOO_DATA if source_type == "odoo" else REST_DATA

        if entity_type not in VALID_ENTITIES:
            self._send_json(404, {
                "error": "unknown_entity",
                "message": f"Entity type '{entity_type}' is not available in /{source_type}/.",
                "available_entities": sorted(VALID_ENTITIES),
            })
            return

        all_records = data_store.get(entity_type, [])

        # Parse pagination: limit and offset
        try:
            limit = int(query.get("limit", [100])[0])
        except (ValueError, IndexError):
            self._send_json(400, {
                "error": "invalid_parameter",
                "message": "Parameter 'limit' must be a positive integer.",
            })
            return

        try:
            offset = int(query.get("offset", [0])[0])
        except (ValueError, IndexError):
            self._send_json(400, {
                "error": "invalid_parameter",
                "message": "Parameter 'offset' must be a non-negative integer.",
            })
            return

        if limit <= 0:
            self._send_json(400, {
                "error": "invalid_parameter",
                "message": "Parameter 'limit' must be a positive integer.",
            })
            return

        if offset < 0:
            self._send_json(400, {
                "error": "invalid_parameter",
                "message": "Parameter 'offset' must be a non-negative integer.",
            })
            return

        # Paginate
        total = len(all_records)
        page_records = all_records[offset : offset + limit]
        next_offset = offset + len(page_records)
        has_more = next_offset < total

        response = {
            "data": page_records,
            "pagination": {
                "offset": offset,
                "limit": limit,
                "total": total,
                "has_more": has_more,
            },
        }
        if has_more:
            response["pagination"]["next_offset"] = next_offset

        self._send_json(200, response)

    def _handle_entity_detail(
        self, source_type: str, entity_type: str, record_id: str
    ) -> None:
        """Handle GET /odoo/<entity>/<id> or /rest/<entity>/<id>."""
        data_store = ODOO_DATA if source_type == "odoo" else REST_DATA

        if entity_type not in VALID_ENTITIES:
            self._send_json(404, {
                "error": "unknown_entity",
                "message": f"Entity type '{entity_type}' is not available in /{source_type}/.",
                "available_entities": sorted(VALID_ENTITIES),
            })
            return

        records = data_store.get(entity_type, [])

        for record in records:
            rec_id = record.get("id")
            if source_type == "odoo":
                try:
                    if rec_id == int(record_id):
                        self._send_json(200, {"data": record})
                        return
                except (ValueError, TypeError):
                    pass
            else:
                if str(rec_id) == record_id:
                    self._send_json(200, {"data": record})
                    return

        self._send_json(404, {
            "error": "not_found",
            "message": f"Record not found: /{source_type}/{entity_type}/{record_id}",
        })

    def _send_json(self, status_code: int, body: dict) -> None:
        """Send a JSON response."""
        payload = json.dumps(body, indent=2, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:
        """Override to use a cleaner log format."""
        print(f"[mock-source] {self.address_string()} - {format % args}")


def main() -> None:
    """Start the mock-source HTTP server."""
    global ODOO_DATA, REST_DATA

    host = os.environ.get("MOCK_SOURCE_HOST", "0.0.0.0")
    port = int(os.environ.get("MOCK_SOURCE_PORT", "8080"))
    data_dir = os.environ.get("MOCK_SOURCE_DATA_DIR", "data/demo")

    print(f"[mock-source] Loading source data from: {data_dir}")
    ODOO_DATA, REST_DATA = load_source_data(data_dir)

    server = HTTPServer((host, port), MockSourceHandler)
    print(f"[mock-source] Starting on {host}:{port}")
    print(f"[mock-source] Entities: {sorted(VALID_ENTITIES)}")
    print(f"[mock-source] Routes: /health, /odoo/{{entity}}, /rest/{{entity}}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[mock-source] Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
