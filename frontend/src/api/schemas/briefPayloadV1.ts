/**
 * The decision payload, version 1, key for key (spec §6.4).
 *
 * Source of truth: `CONTEXT/VS01_IMPLEMENTATION_PLAN.md` §0.6.13.1, which fixes
 * the twelve top-level keys, every nested key and every list order; the frozen
 * projections' key sets are those of `app/intelligence/contract.py`,
 * `app/decisions/reconciler.py`, `app/decisions/payload.py`,
 * `app/relationships/queries.py` and `app/relationships/model.py`.
 *
 * Every object is strict and `Evidence.rule_id` is the only optional key.
 * The payload is never re-hashed here: `payload_hash` is always the API's.
 */

import { z } from 'zod';

import { count, decimalText, integer, isoDate, sha256Hex } from './common';

export const PAYLOAD_VERSION = 1;

export const riskBand = z.enum(['NONE', 'WATCH', 'ELEVATED', 'CRITICAL']);
export const evidenceKind = z.enum([
  'CANONICAL_FACT',
  'DERIVED_RELATIONSHIP',
  'DOCUMENT_SPAN',
  'DETERMINISTIC_RULE',
]);
export const businessFunction = z.enum(['SUPPORT', 'SALES']);
export const stance = z.enum(['ADVANCE', 'RESTRAIN', 'NEUTRAL']);
export const actionId = z.enum([
  'ESCALATE_TO_ACCOUNT_OWNER_PER_SLA',
  'SCHEDULE_EXECUTIVE_SPONSOR_CALL',
  'ASSIGN_DEDICATED_SUPPORT_OWNER',
  'PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED',
  'REVIEW_INVOICE_DISPUTE',
  'ACCELERATE_DEAL_CLOSE',
  'NO_ACTION',
]);
export const linkBasis = z.enum(['ID_TOKEN', 'EXACT_NAME', 'TOPIC']);
export const edgeBasis = z.enum([
  'CANONICAL_FK',
  'SOURCE_KEY_JOIN',
  'DERIVED_TEXT_MATCH',
  'DERIVED_TOPIC_MATCH',
]);
export const linkConfidence = z.enum(['HIGH', 'SUPPORTING']);
export const edgeType = z.enum([
  'customer_has_ticket',
  'customer_has_deal',
  'customer_has_project',
  'customer_owned_by',
  'ticket_assigned_to',
  'employee_reports_to',
  'deal_owned_by',
]);

export const recordCitation = z.strictObject({
  kind: z.literal('record'),
  entity: z.string(),
  id: z.string(),
  field: z.string(),
});
export const documentCitation = z.strictObject({
  kind: z.literal('document'),
  document_id: z.string(),
  start: count,
  end: count,
});
export const citation = z.discriminatedUnion('kind', [recordCitation, documentCitation]);

export const evidence = z.strictObject({
  kind: evidenceKind,
  citation,
  rule_id: z.string().optional(),
});

export const entityRef = z.strictObject({ entity: z.string(), id: z.string() });

export const position = z.strictObject({
  function: businessFunction,
  stance,
  proposed_action: actionId,
  object_ref: z.string(),
  rationale: z.string(),
  evidence: z.array(evidence),
});

export const conflict = z.strictObject({
  object_ref: z.string(),
  positions: z.array(position),
});

export const resolution = z.strictObject({
  policy_id: z.string(),
  conflict,
  resolved_action: actionId,
  prevailing: position,
  dissent: z.array(position),
  rationale: z.string(),
  evidence: z.array(evidence),
});

export const worthiness = z.strictObject({
  band: riskBand,
  active_deal_count: count,
  active_project_count: count,
  executive_worthy: z.boolean(),
});

export const rankingKey = z.tuple([integer, integer, integer, z.string()]);

export const reconciliation = z.strictObject({
  customer: entityRef,
  policy_version: integer,
  ordered_positions: z.array(position),
  conflicts: z.array(conflict),
  resolutions: z.array(resolution),
  resolved_positions: z.array(position),
  dissent: z.array(position),
  worthiness,
  ranking_key: rankingKey,
});

export const money = z.strictObject({ amount: decimalText, currency: z.string() });

export const dealSignal = z.strictObject({
  id: z.string(),
  stage: z.string(),
  probability: decimalText,
  amount: money,
});

/** `SignalSet.to_payload()`: exactly 17 keys. */
export const signals = z.strictObject({
  open_ticket_count: count,
  open_high_priority_count: count,
  high_priority_total: count,
  tickets_in_lookback: count,
  max_tickets_in_14d_window: count,
  sla_breach_count: count,
  open_sla_breach_high_count: count,
  stale_open_ticket_count: count,
  active_project_count: count,
  policy_escalation_state: z.boolean(),
  days_since_last_ticket: integer.nullable(),
  dominant_ticket_category: z.string().nullable(),
  deal_under_pressure: z.boolean(),
  active_deal_count: count,
  active_deals: z.array(dealSignal),
  exposure_by_currency: z.record(z.string(), money),
  contract_document_ids: z.array(z.string()),
});

/** `DerivedLink.to_payload()`: exactly 10 keys; `document_type` is not carried. */
export const documentEvidence = z.strictObject({
  source: entityRef,
  target: entityRef,
  basis: linkBasis,
  edge_basis: edgeBasis,
  confidence: linkConfidence,
  matched_token: z.string(),
  evidence: z.array(evidence),
  source_system: z.string(),
  layer1_fingerprint: sha256Hex,
  linker_version: z.string(),
});

export const citedSpan = z.strictObject({ target: z.string(), citation: documentCitation });

export const ticket = z.strictObject({
  id: z.string(),
  priority: z.string().nullable(),
  category: z.string().nullable(),
  is_open: z.boolean(),
  breaches_sla: z.boolean(),
  created_date: isoDate,
  evidence: z.array(evidence),
});

export const escalationWindow = z.strictObject({ start: isoDate, end: isoDate, count });

export const ticketSpan = z.strictObject({
  ticket_ids: z.array(z.string()),
  ticket_count: count,
  first_ticket_date: isoDate,
  last_ticket_date: isoDate,
  ticket_span_days: count,
  rule: z.string(),
});

export const edge = z.strictObject({
  edge: edgeType,
  source: entityRef,
  target: entityRef,
  basis: edgeBasis,
  carrier_field: z.string(),
  source_system: z.string(),
});

export const escalationPath = z.strictObject({
  customer: entityRef,
  account_owner: entityRef.nullable(),
  account_owner_manager: entityRef.nullable(),
  open_tickets: z.array(entityRef),
  assignees: z.array(entityRef),
  assignee_managers: z.array(entityRef),
  edges: z.array(edge),
});

function countDerivation<T extends string>(fact: T) {
  return z.strictObject({
    fact: z.literal(fact),
    value: count,
    rule: z.string(),
    ticket_ids: z.array(z.string()),
  });
}

export const categoryDerivation = z.strictObject({
  fact: z.literal('dominant_ticket_category'),
  value: z.string().nullable(),
  rule: z.string(),
  lookback: z.strictObject({ start: isoDate, end: isoDate }),
  category_counts: z.record(z.string(), count),
  ticket_ids: z.array(z.string()),
});

/** Exactly five derivations, in this order (§0.6.13.1 item 6). */
export const derivations = z.tuple([
  countDerivation('open_ticket_count'),
  countDerivation('open_high_priority_count'),
  countDerivation('high_priority_total'),
  countDerivation('open_sla_breach_high_count'),
  categoryDerivation,
]);

export const supportEvidence = z.strictObject({
  tickets: z.array(ticket),
  escalation_window: escalationWindow.nullable(),
  ticket_span: ticketSpan.nullable(),
  backlog_ticket_ids: z.array(z.string()),
  escalation_path: escalationPath,
  derivations,
});

export const deal = z.strictObject({
  id: z.string(),
  stage: z.string(),
  probability: decimalText,
  amount: money,
  evidence: z.array(evidence),
});

export const commercialEvidence = z.strictObject({ deals: z.array(deal) });

/** The twelve top-level keys, none ever omitted. */
export const briefPayloadV1 = z.strictObject({
  payload_version: z.literal(PAYLOAD_VERSION),
  scope: z.strictObject({
    source_system: z.string(),
    as_of: isoDate,
    layer1_fingerprint: sha256Hex,
  }),
  versions: z.strictObject({ rules: integer, linker: z.string(), policy: integer }),
  customer: entityRef,
  band: riskBand,
  satisfied_rules: z.array(z.string()),
  signals,
  reconciliation,
  document_evidence: z.array(documentEvidence),
  cited_spans: z.array(citedSpan),
  support_evidence: supportEvidence,
  commercial_evidence: commercialEvidence,
});

export type RiskBand = z.infer<typeof riskBand>;
export type Evidence = z.infer<typeof evidence>;
export type Citation = z.infer<typeof citation>;
export type Position = z.infer<typeof position>;
export type Signals = z.infer<typeof signals>;
export type BriefPayloadV1 = z.infer<typeof briefPayloadV1>;
