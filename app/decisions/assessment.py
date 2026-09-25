"""
The assessment run: the one impure M7 module (VS-01 M7, §0.6.3).

`run_assessment` resolves one scope, derives its document links once, builds
and reconciles every customer's contexts, and persists what M3, M5 and M6
decided: one assessment per customer, its positions, and -- for a band of
WATCH or above -- one brief whose payload is hashed and whose every citation
resolves. It decides nothing itself. Worthiness, both orders, every conflict,
resolution and dissent are M6's, the band and the signals are M3's and M5's,
and they are stored verbatim (§0.5.1).

**The sequence is §0.6.3's, and nothing else runs.** `derive_and_persist`
runs exactly once, before any context is built, because S14 reads the links
it writes (§0.4.3). `build_contexts` and `reconcile` own the signals, the
band, the analysts, detection and ordering, so none of those is called here.
The one exception is §0.6.4's: for a briefed customer, `compute_signals` is
read for exactly two fields, the escalation window and the backlog ticket
ids, and its signal values are never read -- the contexts are authoritative.

**Only the assessment's own links are evidence** (§0.6.13.1). A brief's
`document_evidence` holds the links stamped with this scope's fingerprint and
this configuration's linker version. Frozen S14 still reads every persisted
link, which §A29 records.

**Every citation in a brief resolves before the brief is written** (§0.6.9),
in ascending wire-form order so the first failure named is deterministic. A
record citation resolves when its row exists in the scope's source system
and, for the four fields a brief states or derives from, when the field is
not NULL (DR21). A document citation resolves through M4 unchanged. A cited
span is located as exactly one occurrence of its phrase, and its resolved
text must equal that phrase (§0.6.13.3).

**The transaction is the caller's.** Nothing here opens, commits, rolls back,
begins or closes anything, and every write goes through M7's repositories.
Any failure propagates unwrapped -- this module catches nothing -- so the
caller's rollback leaves no partial assessment durable (§A23).

**Events are emitted last** (§0.6.13.6): after every write of every customer
has succeeded, INFO through `log_event` only, in run order. A run that raises
emits nothing. Logging is not transactional, so a line can describe a run
the caller then rolls back (§A29).

**This module names neither `AnalystContexts` nor `Reconciliation`**
(§0.6.2 grants both, as types, to `payload.py` alone). Both are held only
where `build_contexts` and `reconcile` return them, inside `run_assessment`,
and every helper takes M1 contract types or plain values.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.analysts import build_contexts
from app.core.logging import log_event
from app.decisions import (
    ConflictPolicy,
    default_conflict_policy,
    order_reconciliations,
    reconcile,
)
from app.decisions.brief import TEMPLATE_VERSION, render_brief
from app.decisions.payload import (
    SpanTarget,
    applicable_targets,
    build_payload,
    first_occurrences,
    payload_citations,
    payload_hash,
)
from app.evidence import (
    CitationResolutionError,
    citable_text,
    derive_and_persist,
    documents_for,
    resolve_document_citation,
)
from app.intelligence import (
    DEFAULT_SOURCE_SYSTEM,
    RiskRulesConfig,
    Scope,
    default_risk_rules,
    resolve_scope,
    utc_date,
)
from app.intelligence.contract import (
    ConflictResolution,
    DerivedLink,
    DocumentCitation,
    Position,
    RecordCitation,
    RiskBand,
    canonical_json,
)
from app.intelligence.signals import compute_signals, customers_in_scope
from app.persistence.repositories.citation_reads import (
    document_texts,
    field_nullness,
    ticket_created_at,
)
from app.persistence.repositories.risk_assessments import (
    AssessmentRow,
    BriefRow,
    PositionRow,
    insert_assessment,
    insert_brief,
    insert_positions,
)
from app.relationships import escalation_path

logger = logging.getLogger(__name__)

#: A brief is generated for a band at or above this (§0 defect 11).
BRIEF_BAND = RiskBand.WATCH

#: DR21: the cited fields a brief states or derives from, which must therefore
#: hold a value. Every other citable field may be NULL.
NON_NULL_FIELDS = frozenset({
    ("documents", "body_text"),
    ("support_tickets", "created_at"),
    ("deals", "amount"),
    ("deals", "currency"),
})


@dataclass(frozen=True)
class AssessmentResult:
    """One customer's outcome, in `order_reconciliations()` order (§0.6.3)."""

    assessment_id: UUID
    created: bool
    brief_id: UUID | None
    payload_hash: str | None


@dataclass(frozen=True)
class _Brief:
    """What a customer's brief_generated event reports."""

    payload_hash: str
    citation_count: int
    created: bool


@dataclass(frozen=True)
class _Outcome:
    """What one customer's events report, each field verbatim from M6 (§0.6.13.6)."""

    customer: str
    policy_version: int
    resolutions: tuple[ConflictResolution, ...]
    brief: _Brief | None


def run_assessment(
    session: Session,
    *,
    as_of: date | None,
    source_system: str = DEFAULT_SOURCE_SYSTEM,
    customer_source_id: str | None = None,
    expected_fingerprint: str | None = None,
    config: RiskRulesConfig | None = None,
    policy: ConflictPolicy | None = None,
) -> tuple[AssessmentResult, ...]:
    """
    Assess every customer in scope, or the one named, and persist the results.

    Unpinned when `expected_fingerprint` is None; otherwise a snapshot that
    is not the expected one raises FingerprintMismatchError before anything
    is derived. Returns one result per customer assessed, in
    `order_reconciliations()` order.
    """
    rules = config if config is not None else default_risk_rules()
    decisions = policy if policy is not None else default_conflict_policy()
    scope = resolve_scope(
        session,
        source_system=source_system,
        as_of=as_of,
        expected_fingerprint=expected_fingerprint,
    )
    inserted = derive_and_persist(session, scope, config=rules)
    customers = (
        (customer_source_id,) if customer_source_id is not None
        else customers_in_scope(session, scope)
    )
    contexts = {
        customer: build_contexts(session, scope, customer, config=rules)
        for customer in customers
    }
    reconciliations = order_reconciliations(
        reconcile(contexts[customer], policy=decisions) for customer in customers
    )
    results: list[AssessmentResult] = []
    outcomes: list[_Outcome] = []
    for reconciliation in reconciliations:
        customer = reconciliation.customer.source_id
        context = contexts[customer]
        commercial = context.commercial
        # §0.6.5's columns, each taken verbatim from the scope, the contexts or M6.
        assessment_id, created = insert_assessment(session, AssessmentRow(
            customer_source_id=customer,
            as_of=scope.as_of,
            source_system=scope.source_system,
            layer1_fingerprint=scope.layer1_fingerprint,
            rules_version=rules.rules_version,
            linker_version=rules.linker_version,
            band=commercial.band,
            executive_worthy=reconciliation.worthiness.executive_worthy,
            signals=commercial.signals.to_payload(),
            satisfied_rules=list(commercial.satisfied_rules),
            ranking_key=list(reconciliation.ranking_key),
        ))
        if created:
            insert_positions(
                session, assessment_id, _position_rows(reconciliation.ordered_positions)
            )
        brief_id: UUID | None = None
        brief: _Brief | None = None
        if RiskBand(commercial.band).at_least(BRIEF_BAND):
            # Step 9: read §0.6.4's inputs, build the payload, resolve it and
            # render it -- whether or not the brief already exists.
            measured = compute_signals(session, scope, customer, config=rules)
            window = measured.escalation_window
            links = _own_links(session, scope, rules, customer)
            targets = applicable_targets(reconciliation, links)
            spans = _locate(session, scope, targets)
            payload = build_payload(
                scope=scope,
                config=rules,
                contexts=context,
                reconciliation=reconciliation,
                links=links,
                spans=spans,
                created_dates=_ticket_dates(
                    session, scope, [fact.source_id for fact in context.support.tickets]
                ),
                escalation_window=None if window is None else window.to_payload(),
                backlog_ticket_ids=measured.backlog_ticket_ids,
                escalation_path=escalation_path(session, scope, customer).to_payload(),
            )
            resolved, citation_count = _resolve(session, scope, payload)
            narrative = render_brief(payload, _span_texts(targets, spans, resolved))
            digest = payload_hash(payload)
            brief_id, brief_created = insert_brief(session, BriefRow(
                assessment_id=assessment_id,
                policy_version=reconciliation.policy_version,
                template_version=TEMPLATE_VERSION,
                decision_payload=payload,
                payload_hash=digest,
                narrative=narrative,
            ))
            brief = _Brief(payload_hash=digest, citation_count=citation_count,
                           created=brief_created)
        results.append(AssessmentResult(
            assessment_id=assessment_id,
            created=created,
            brief_id=brief_id,
            payload_hash=None if brief is None else brief.payload_hash,
        ))
        outcomes.append(_Outcome(
            customer=customer,
            policy_version=reconciliation.policy_version,
            resolutions=reconciliation.resolutions,
            brief=brief,
        ))
    _emit(scope, rules, inserted, outcomes)
    return tuple(results)


def _position_rows(ordered_positions: Sequence[Position]) -> list[PositionRow]:
    """Every ordered position, at its index from 0, with its evidence as projected."""
    rows: list[PositionRow] = []
    for ordinal, position in enumerate(ordered_positions):
        projected = position.to_payload()
        rows.append(PositionRow(
            ordinal=ordinal,
            function=str(position.function),
            stance=str(position.stance),
            proposed_action=str(position.proposed_action),
            object_ref=position.object_ref,
            rationale=position.rationale,
            citations=projected["evidence"],
        ))
    return rows


def _own_links(
    session: Session, scope: Scope, rules: RiskRulesConfig, customer: str
) -> tuple[DerivedLink, ...]:
    """The customer's links stamped with this scope's fingerprint and linker version (§0.6.13.1)."""
    return tuple(
        linked.link for linked in documents_for(session, scope, customer)
        if linked.link.layer1_fingerprint == scope.layer1_fingerprint
        and linked.link.linker_version == rules.linker_version
    )


def _ticket_dates(
    session: Session, scope: Scope, visible_ticket_ids: Sequence[str]
) -> dict[str, date]:
    """
    The UTC creation date of every visible ticket, through §0.6.5's authorised read.

    The ids are the context's visible tickets, so this decides no membership.
    A ticket the read does not return, or returns with no created_at, fails
    the brief rather than letting it invent a date (OPEN-M7-3).
    """
    ticket_ids = sorted(visible_ticket_ids)
    created = ticket_created_at(session, scope.source_system, ticket_ids)
    dates: dict[str, date] = {}
    for ticket_id in ticket_ids:
        if ticket_id not in created:
            raise CitationResolutionError(
                f"visible ticket {ticket_id} is not in source_system {scope.source_system!r}, "
                f"so its creation date cannot be read"
            )
        moment = created[ticket_id]
        if moment is None:
            raise CitationResolutionError(
                f"visible ticket {ticket_id} has no created_at, so the brief's ticket dates "
                f"and ticket span cannot be derived, and none is invented"
            )
        dates[ticket_id] = utc_date(moment)
    return dates


def _locate(
    session: Session, scope: Scope, targets: Sequence[SpanTarget]
) -> dict[str, DocumentCitation]:
    """
    Each applicable target's span: exactly one occurrence of its phrase (§0.6.13.3).

    Zero or several occurrences, or a document absent from the source system,
    raise M4's CitationResolutionError naming the target and the document.
    There is no substitute span and no whole-document fallback.
    """
    texts = document_texts(session, scope.source_system, [target.document_id for target in targets])
    spans: dict[str, DocumentCitation] = {}
    for target in targets:
        if target.document_id not in texts:
            raise CitationResolutionError(
                f"cited-span target {target.name} names {target.document_id}, which is not in "
                f"source_system {scope.source_system!r}"
            )
        title, body_text = texts[target.document_id]
        found = first_occurrences(citable_text(title, body_text), target.phrase)
        if not found:
            raise CitationResolutionError(
                f"cited-span target {target.name}: its phrase does not occur in "
                f"{target.document_id}, and no substitute span is taken"
            )
        if len(found) > 1:
            raise CitationResolutionError(
                f"cited-span target {target.name}: its phrase occurs more than once in "
                f"{target.document_id}, and exactly one occurrence is required"
            )
        (start,) = found
        spans[target.name] = DocumentCitation(
            document_id=target.document_id, start=start, end=start + len(target.phrase)
        )
    return spans


def _resolve(
    session: Session, scope: Scope, payload: Mapping[str, object]
) -> tuple[dict[str, str], int]:
    """
    Resolve every distinct citation in ascending wire-form order (§0.6.9).

    Returns the resolved text of each document citation, keyed by its wire
    form, and how many distinct citations were resolved.
    """
    citations = payload_citations(payload)
    texts: dict[str, str] = {}
    for citation in citations:
        if isinstance(citation, RecordCitation):
            _resolve_record(session, scope, citation)
        else:
            texts[canonical_json(citation.to_payload())] = resolve_document_citation(
                session, scope, citation
            )
    return texts, len(citations)


def _resolve_record(session: Session, scope: Scope, citation: RecordCitation) -> None:
    """
    A record citation resolves iff its row is in scope and its field meets DR21's NULL rule.

    NULL is accepted in general -- M5 cites an open ticket's empty
    `resolved_at` as the ground for "open" -- except for the fields a brief
    states or derives from, keyed by `entity.field` wherever they are cited.
    """
    null = field_nullness(
        session, scope.source_system, citation.entity_type, citation.source_id,
        citation.field_name,
    )
    if null is None:
        raise CitationResolutionError(
            f"citation names {citation.entity_type} {citation.source_id}, which is not in "
            f"source_system {scope.source_system!r}"
        )
    if null and (citation.entity_type, citation.field_name) in NON_NULL_FIELDS:
        raise CitationResolutionError(
            f"citation names {citation.entity_type} {citation.source_id} "
            f"{citation.field_name}, which is NULL; the brief states or derives that value, "
            f"so it must exist"
        )


def _span_texts(
    targets: Sequence[SpanTarget],
    spans: Mapping[str, DocumentCitation],
    resolved: Mapping[str, str],
) -> dict[str, str]:
    """Each cited span's resolved text, which must equal its phrase exactly (§0.6.13.3)."""
    texts: dict[str, str] = {}
    for target in targets:
        text = resolved[canonical_json(spans[target.name].to_payload())]
        if text != target.phrase:
            raise CitationResolutionError(
                f"cited-span target {target.name} resolves in {target.document_id} to text "
                f"other than its phrase"
            )
        texts[target.name] = text
    return texts


def _emit(
    scope: Scope,
    rules: RiskRulesConfig,
    inserted: int,
    outcomes: Sequence[_Outcome],
) -> None:
    """Step 11: §0.6.13.6's events, in run order, once every write has succeeded."""
    log_event(
        logger, logging.INFO, "vs01.scope_resolved",
        source_system=scope.source_system,
        as_of=scope.as_of.isoformat(),
        layer1_fingerprint=scope.layer1_fingerprint,
        as_of_source=str(scope.as_of_source),
    )
    log_event(
        logger, logging.INFO, "vs01.links_derived",
        source_system=scope.source_system,
        layer1_fingerprint=scope.layer1_fingerprint,
        linker_version=rules.linker_version,
        inserted=inserted,
    )
    for outcome in outcomes:
        for resolution in outcome.resolutions:
            log_event(
                logger, logging.INFO, "vs01.conflict_detected",
                customer=outcome.customer,
                object_ref=resolution.conflict.object_ref,
                policy_id=resolution.policy_id,
                policy_version=outcome.policy_version,
            )
            log_event(
                logger, logging.INFO, "vs01.conflict_resolved",
                customer=outcome.customer,
                object_ref=resolution.conflict.object_ref,
                policy_id=resolution.policy_id,
                policy_version=outcome.policy_version,
                resolved_action=str(resolution.resolved_action),
            )
        if outcome.brief is not None:
            log_event(
                logger, logging.INFO, "vs01.brief_generated",
                customer=outcome.customer,
                payload_hash=outcome.brief.payload_hash,
                citation_count=outcome.brief.citation_count,
                created=outcome.brief.created,
            )
