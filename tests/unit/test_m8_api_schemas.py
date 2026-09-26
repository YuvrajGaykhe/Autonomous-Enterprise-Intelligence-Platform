"""
M8's API models and error vocabulary, without a database (§0.7.8, §0.7.9, §0.7.13).

The request models are closed (extra="forbid") and bounded exactly as
§0.7.8's request table states. The schemas module imports no Layer 2
package, so it declares its own copies of M8's decision vocabulary and
bounds; each copy is pinned here equal to the value app.decisions.approval,
M1's scope or M7's hash defines, so the two can never drift apart.
"""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app.api.errors import ErrorCode
from app.api.v1.schemas import (
    AssessmentDetailResponse,
    AssessmentListItem,
    AssessmentRunRequest,
    BriefResponse,
    DecisionRequest,
    DecisionResponse,
    RiskDecision,
    RiskDecisionStatus,
)
from app.decisions.approval import MAX_ACTOR_CHARS, MAX_NOTE_CHARS, Decision, DecisionStatus
from app.decisions.payload import payload_hash
from app.intelligence import RiskBand
from app.intelligence.scope import DEFAULT_SOURCE_SYSTEM
from app.main import create_app

DIGEST = payload_hash({"payload_version": 1})


def decision_body(**changes: object) -> dict[str, object]:
    body: dict[str, object] = {"actor": "reviewer one", "decision": "APPROVED",
                               "payload_hash": DIGEST}
    body.update(changes)
    return body


def refused(model, body: dict[str, object]) -> list[tuple[str, ...]]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(body)
    return [tuple(str(part) for part in error["loc"]) for error in caught.value.errors()]


# ---------------------------------------------------------------------------
# The error vocabulary (§0.7.9)
# ---------------------------------------------------------------------------


M8_ERROR_CODES = ("ASSESSMENT_NOT_FOUND", "BRIEF_NOT_FOUND", "CUSTOMER_NOT_FOUND",
                  "SCOPE_UNRESOLVED", "PAYLOAD_HASH_CONFLICT", "DECISION_CONFLICT")
LAYER_1_ERROR_CODES = ("INVALID_REQUEST", "NOT_FOUND", "METHOD_NOT_ALLOWED", "HTTP_ERROR",
                       "INTERNAL_ERROR", "SOURCE_NOT_FOUND", "SOURCE_MISCONFIGURED",
                       "RUN_NOT_FOUND", "UNSUPPORTED_OPTION", "INVALID_INGESTION_REQUEST",
                       "ENTITY_NOT_FOUND")


def test_m8_adds_exactly_six_error_codes_after_layer_1s():
    assert [code.value for code in ErrorCode] == [*LAYER_1_ERROR_CODES, *M8_ERROR_CODES]
    assert all(ErrorCode[name].value == name for name in M8_ERROR_CODES)


# ---------------------------------------------------------------------------
# Mirrored vocabulary and bounds
# ---------------------------------------------------------------------------


def test_the_mirrored_decision_enum_equals_approvals():
    assert [(member.name, member.value) for member in RiskDecision] == [
        (member.name, member.value) for member in Decision]


def test_the_mirrored_status_enum_equals_approvals():
    assert [(member.name, member.value) for member in RiskDecisionStatus] == [
        (member.name, member.value) for member in DecisionStatus]


def test_the_schema_bounds_equal_approvals_and_the_scopes_default():
    fields = DecisionRequest.model_json_schema()["properties"]
    assert fields["actor"]["maxLength"] == MAX_ACTOR_CHARS
    assert fields["note"]["anyOf"][0]["maxLength"] == MAX_NOTE_CHARS
    assert AssessmentRunRequest.model_fields["source_system"].default == DEFAULT_SOURCE_SYSTEM


# ---------------------------------------------------------------------------
# AssessmentRunRequest
# ---------------------------------------------------------------------------


def test_as_of_is_required_but_may_be_null():
    assert refused(AssessmentRunRequest, {}) == [("as_of",)]
    request = AssessmentRunRequest.model_validate({"as_of": None})

    assert request == AssessmentRunRequest(as_of=None, source_system="csv_demo",
                                           customer_source_id=None)


def test_a_full_assessment_request_is_read_as_sent():
    request = AssessmentRunRequest.model_validate(
        {"as_of": "2026-09-18", "source_system": "rest_mock", "customer_source_id": "CUST-007"})

    assert (request.as_of, request.source_system, request.customer_source_id) == (
        date(2026, 9, 18), "rest_mock", "CUST-007")


@pytest.mark.parametrize(("body", "location"), [
    ({"as_of": None, "expected_fingerprint": "a" * 64}, ("expected_fingerprint",)),
    ({"as_of": None, "policy": {}}, ("policy",)),
    ({"as_of": None, "source_system": ""}, ("source_system",)),
    ({"as_of": None, "source_system": "s" * 101}, ("source_system",)),
    ({"as_of": None, "customer_source_id": ""}, ("customer_source_id",)),
    ({"as_of": None, "customer_source_id": "c" * 256}, ("customer_source_id",)),
    ({"as_of": "18/09/2026"}, ("as_of",)),
])
def test_the_assessment_request_is_closed_and_bounded(body, location):
    assert refused(AssessmentRunRequest, body) == [location]


def test_the_assessment_request_bounds_are_inclusive():
    request = AssessmentRunRequest.model_validate(
        {"as_of": None, "source_system": "s" * 100, "customer_source_id": "c" * 255})

    assert (len(request.source_system), len(request.customer_source_id or "")) == (100, 255)


# ---------------------------------------------------------------------------
# DecisionRequest
# ---------------------------------------------------------------------------


def test_a_decision_request_is_read_as_sent_with_its_defaults():
    request = DecisionRequest.model_validate(decision_body())

    assert request == DecisionRequest(actor="reviewer one", decision=RiskDecision.APPROVED,
                                      note=None, payload_hash=DIGEST, supersedes_id=None)


def test_the_actor_is_not_validated_as_an_email_and_is_kept_verbatim():
    for actor in ("  reviewer  ", "not an email", "a", "x" * MAX_ACTOR_CHARS):
        assert DecisionRequest.model_validate(decision_body(actor=actor)).actor == actor


@pytest.mark.parametrize("missing", ["actor", "decision", "payload_hash"])
def test_actor_decision_and_payload_hash_are_required(missing):
    body = decision_body()
    del body[missing]

    assert refused(DecisionRequest, body) == [(missing,)]


@pytest.mark.parametrize(("changes", "location"), [
    ({"actor": ""}, ("actor",)),
    ({"actor": "x" * (MAX_ACTOR_CHARS + 1)}, ("actor",)),
    ({"note": "n" * (MAX_NOTE_CHARS + 1)}, ("note",)),
    ({"decision": "PENDING"}, ("decision",)),
    ({"decision": "approved"}, ("decision",)),
    ({"payload_hash": DIGEST.upper()}, ("payload_hash",)),
    ({"payload_hash": DIGEST[:-1]}, ("payload_hash",)),
    ({"payload_hash": DIGEST + "0"}, ("payload_hash",)),
    ({"payload_hash": "g" * 64}, ("payload_hash",)),
    ({"supersedes_id": "not-a-uuid"}, ("supersedes_id",)),
    ({"decided_at": "2026-09-25T09:30:00Z"}, ("decided_at",)),
    ({"status": "APPROVED"}, ("status",)),
])
def test_the_decision_request_is_closed_and_bounded(changes, location):
    assert refused(DecisionRequest, decision_body(**changes)) == [location]


def test_the_decision_request_bounds_are_inclusive():
    request = DecisionRequest.model_validate(decision_body(
        note="n" * MAX_NOTE_CHARS, decision="REJECTED", supersedes_id=str(uuid.UUID(int=1))))

    assert (len(request.note or ""), request.decision, request.supersedes_id) == (
        MAX_NOTE_CHARS, RiskDecision.REJECTED, uuid.UUID(int=1))


# ---------------------------------------------------------------------------
# Response models: exact fields, in §0.7.8's order
# ---------------------------------------------------------------------------


ASSESSMENT_FIELDS = ("id", "customer_source_id", "as_of", "source_system", "layer1_fingerprint",
                     "rules_version", "linker_version", "band", "executive_worthy", "ranking_key")


@pytest.mark.parametrize(("model", "fields"), [
    (AssessmentListItem, (*ASSESSMENT_FIELDS, "brief_ids")),
    (AssessmentDetailResponse, (*ASSESSMENT_FIELDS, "satisfied_rules", "signals", "positions",
                                "briefs")),
    (BriefResponse, ("id", "assessment_id", "status", "decision_status", "policy_version",
                     "template_version", "payload_hash", "payload", "narrative", "citations")),
    (DecisionResponse, ("id", "brief_id", "payload_hash", "actor", "decision", "note",
                        "decided_at", "supersedes_id")),
], ids=lambda value: getattr(value, "__name__", ""))
def test_each_response_model_has_exactly_its_fields(model, fields):
    assert tuple(model.model_fields) == fields


# ---------------------------------------------------------------------------
# The published contract of the six operations (§0.7.8)
# ---------------------------------------------------------------------------


RISK = "/api/v1/risk"
ERROR_REF = {"$ref": "#/components/schemas/ErrorResponse"}

#: Each operation's documented statuses, and the model its success statuses reference.
OPERATIONS = {
    ("post", f"{RISK}/assessments"): ({"200", "201", "422", "500"}, "AssessmentRunResponse"),
    ("get", f"{RISK}/assessments"): ({"200", "422"}, "AssessmentListResponse"),
    ("get", f"{RISK}/assessments/{{assessment_id}}"): (
        {"200", "404", "422"}, "AssessmentDetailResponse"),
    ("get", f"{RISK}/briefs/{{brief_id}}"): ({"200", "404", "422"}, "BriefResponse"),
    ("post", f"{RISK}/briefs/{{brief_id}}/decision"): (
        {"201", "404", "409", "422", "500"}, "DecisionResponse"),
    ("get", f"{RISK}/briefs/{{brief_id}}/decisions"): (
        {"200", "404", "422"}, "DecisionHistoryResponse"),
}


@pytest.fixture(scope="module")
def spec() -> dict:
    return create_app(sessions=sessionmaker()).openapi()


def _content(response: dict) -> dict:
    return response["content"]["application/json"]["schema"]


def test_exactly_the_six_risk_operations_are_published_under_one_tag(spec):
    published = {(method, path): operation for path, methods in spec["paths"].items()
                 if path.startswith(RISK) for method, operation in methods.items()}

    assert set(published) == set(OPERATIONS)
    assert {tuple(operation["tags"]) for operation in published.values()} == {("risk",)}


@pytest.mark.parametrize(("method", "path"), sorted(OPERATIONS))
def test_each_operation_documents_its_statuses_and_every_error_is_the_envelope(spec, method,
                                                                               path):
    statuses, model = OPERATIONS[(method, path)]
    responses = spec["paths"][path][method]["responses"]

    assert set(responses) == statuses
    for status, response in responses.items():
        expected = ERROR_REF if int(status) >= 400 else {"$ref": f"#/components/schemas/{model}"}
        assert _content(response) == expected, status


@pytest.mark.parametrize(("path", "model", "required"), [
    (f"{RISK}/assessments", "AssessmentRunRequest", ["as_of"]),
    (f"{RISK}/briefs/{{brief_id}}/decision", "DecisionRequest",
     ["actor", "decision", "payload_hash"]),
])
def test_each_request_body_is_required_closed_and_names_its_required_fields(spec, path, model,
                                                                            required):
    body = spec["paths"][path]["post"]["requestBody"]
    schema = spec["components"]["schemas"][model]

    assert body["required"] is True
    assert _content(body) == {"$ref": f"#/components/schemas/{model}"}
    assert schema["additionalProperties"] is False
    assert schema["required"] == required


def test_the_listing_takes_three_optional_filters_and_the_page_window(spec):
    parameters = {parameter["name"]: parameter
                  for parameter in spec["paths"][f"{RISK}/assessments"]["get"]["parameters"]}
    band = spec["components"]["schemas"]["RiskBand"]

    assert list(parameters) == ["as_of", "band", "executive_worthy", "limit", "offset"]
    assert not any(parameter["required"] for parameter in parameters.values())
    assert band["enum"] == [member.value for member in RiskBand]
    assert {key: parameters["limit"]["schema"][key] for key in ("minimum", "maximum", "default")} \
        == {"minimum": 1, "maximum": 500, "default": 50}
    assert {key: parameters["offset"]["schema"][key] for key in ("minimum", "maximum", "default")} \
        == {"minimum": 0, "maximum": 2_147_483_647, "default": 0}


def test_the_brief_payload_and_every_citation_are_published_as_opaque_objects(spec):
    """
    §0.7.8: typing the payload would publish document_evidence[].matched_token,
    which G2's credential-name scan rejects. Nothing inside it is published.
    """
    schemas = spec["components"]["schemas"]
    brief = schemas["BriefResponse"]["properties"]
    opaque = {"type": "object", "additionalProperties": True}

    assert {key: brief["payload"][key] for key in opaque} == opaque
    assert "properties" not in brief["payload"]
    assert {key: brief["citations"]["items"][key] for key in opaque} == opaque
    assert {key: schemas["AssessmentPosition"]["properties"]["citations"]["items"][key]
            for key in opaque} == opaque
    assert "matched_token" not in json.dumps(spec)


@pytest.mark.parametrize("model", ["AssessmentListItem", "AssessmentDetailResponse"])
def test_the_ranking_key_is_published_as_m6s_four_components(spec, model):
    """§0.7.8: (-band rank, -S8, -S4, source_id), three integers and then the source id."""
    key = spec["components"]["schemas"][model]["properties"]["ranking_key"]

    assert key["prefixItems"] == [{"type": "integer"}] * 3 + [{"type": "string"}]
    assert (key["minItems"], key["maxItems"]) == (4, 4)


def test_the_mirrored_enums_are_published_with_approvals_values(spec):
    schemas = spec["components"]["schemas"]

    assert schemas["RiskDecision"]["enum"] == [member.value for member in Decision]
    assert schemas["RiskDecisionStatus"]["enum"] == [member.value for member in DecisionStatus]
    assert schemas["BriefResponse"]["properties"]["decision_status"] == {
        "$ref": "#/components/schemas/RiskDecisionStatus"}
