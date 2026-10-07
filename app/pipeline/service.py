"""
The pipeline view service (VS-02 plan A17.1, A20, A22.2).

pipeline_view answers one question for one source system on one date: what
revenue exposure requires attention. It reads, computes and returns. Nothing
it computes is stored, and it writes no row anywhere (plan A16).

It evaluates in the order of plan A17.1, and the first step that fails
decides the outcome:

    2. configuration       the pipeline rules and the rate set, each loaded
                           on first use and kept for the process
    3. the scope           the frozen resolve_scope, with the caller's date
    5. facts and validity  the deals, their two edges and the stored bands
                           are read; then stage 1 of the aggregation, the
                           stage of every deal counted, and every stored
                           band, in that order (OD-M3-1)
    6. the rates           every currency an open valued deal holds must
                           have one. All that lack one are named at once
    7. the view            the canonical object, its hash, the event

So a data-validity error is never reported as a missing rate, and a missing
rate never leaves a partial figure behind. No error is caught or translated
here: giving one a status is the route's (VS02-M4).

This is one of the two modules of app/pipeline that accept a session (plan
A19 item 5). The session and its transaction are the caller's. It is handed
to resolve_scope and to the two readers of app.pipeline.facts and is used
for nothing else: nothing here commits, rolls back, flushes, begins or
closes.

One event is logged, after the view is built and before it is returned. A
call that fails logs nothing. The event holds no amount and no customer.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.fx.errors import FxRateMissingError
from app.fx.rates import default_rate_set
from app.intelligence import default_risk_rules, resolve_scope
from app.normalization.config import default_config
from app.pipeline.config import default_pipeline_rules
from app.pipeline.facts import read_band_facts, read_deal_facts, valued_deal
from app.pipeline.view import (
    PipelineView,
    build_view,
    check_data,
    citations,
    limitation_texts,
    view_hash,
)

logger = logging.getLogger(__name__)


def pipeline_view(session: Session, *, as_of: date, source_system: str) -> PipelineView:
    """
    The view of one source system at one date, with its hash, texts and citations.

    Raises the loaders' own errors for a refused configuration file,
    PipelineDataError or the frozen MoneyValue's refusal for data that makes
    a correct view impossible, and FxRateMissingError naming every currency
    of an open valued deal that the rate set holds no rate for.
    """
    rules = default_pipeline_rules()
    rate_set = default_rate_set()
    scope = resolve_scope(session, source_system=source_system, as_of=as_of)
    risk_rules = default_risk_rules()
    stages = default_config().fields["deals"]["stage"].enum_values

    facts = read_deal_facts(session, scope)
    bands = read_band_facts(session, scope, rules_version=risk_rules.rules_version,
                            linker_version=risk_rules.linker_version)
    check_data(facts, bands, stages)

    held = {deal.currency for deal in map(valued_deal, facts) if deal is not None}
    missing = held - set(rate_set.rates)
    if missing:
        raise FxRateMissingError(missing, rate_set.rate_set_version)

    view = build_view(scope=scope, facts=facts, bands=bands, rate_set=rate_set, rules=rules,
                      rules_version=risk_rules.rules_version,
                      linker_version=risk_rules.linker_version, stage_vocabulary=stages)
    built = PipelineView(view=view, view_hash=view_hash(view),
                         limitation_texts=limitation_texts(view), citations=citations(view))
    log_event(
        logger, logging.INFO, "vs02.pipeline_view_built",
        source_system=scope.source_system,
        as_of=scope.as_of.isoformat(),
        layer1_fingerprint=scope.layer1_fingerprint,
        pipeline_version=rules.pipeline_version,
        rate_set_version=rate_set.rate_set_version,
        open_deal_count=view["deal_counts"]["open"],
        unvalued_deal_count=view["deal_counts"]["open_unvalued"],
        view_hash=built.view_hash,
    )
    return built
