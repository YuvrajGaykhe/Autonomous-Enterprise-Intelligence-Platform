/**
 * The brief view model (spec §7.3; DERIVED from `VS01_IMPLEMENTATION_PLAN.md` §0.6.13.1 and
 * `app/decisions/brief.py`).
 *
 * Each section maps to exact payload paths, in the brief's own section order. Values are shown as
 * the payload states them; the only formatting is the brief's own: a signal reads `true`, `false`,
 * `none` or its number, and money is `USD 5,361.44`, per currency, never totalled.
 */

import type { BriefPayloadV1, Position, Signals } from '@/api/schemas/briefPayloadV1';
import type { BriefResponse } from '@/api/schemas/risk';

import { exposureLines, formatMoney } from './money';

type Payload = BriefPayloadV1;
type Reconciliation = Payload['reconciliation'];
type SupportEvidence = Payload['support_evidence'];

/** S1–S15 as the risk state lists them (`RISK_SIGNALS`); S12 and S14 have their own sections. */
export const RISK_SIGNALS = [
  ['S1', 'open_ticket_count'],
  ['S2', 'open_high_priority_count'],
  ['S2b', 'high_priority_total'],
  ['S3', 'tickets_in_lookback'],
  ['S4', 'max_tickets_in_14d_window'],
  ['S5', 'policy_escalation_state'],
  ['S6', 'days_since_last_ticket'],
  ['S7', 'sla_breach_count'],
  ['S8', 'open_sla_breach_high_count'],
  ['S9', 'stale_open_ticket_count'],
  ['S10', 'dominant_ticket_category'],
  ['S11', 'active_deal_count'],
  ['S13', 'active_project_count'],
  ['S15', 'deal_under_pressure'],
] as const satisfies readonly (readonly [string, keyof Signals])[];

export interface SignalRow {
  id: string;
  key: keyof Signals;
  value: string;
}

/** A scalar signal as the brief writes it (`_signal_value`). */
export function signalValue(value: string | number | boolean | null): string {
  if (value === null) return 'none';
  return String(value);
}

export function signalRows(signals: Signals): SignalRow[] {
  return RISK_SIGNALS.map(([id, key]) => ({
    id,
    key,
    value: signalValue(signals[key]),
  }));
}

export interface DerivationView {
  fact: string;
  value: string;
  rule: string;
  ticketIds: string[];
  /** The category derivation's counts and lookback; null for the count derivations. */
  categories: { counts: { category: string; count: number }[]; lookback: string } | null;
}

export function derivationViews(derivations: SupportEvidence['derivations']): DerivationView[] {
  return derivations.map((derivation) =>
    derivation.fact === 'dominant_ticket_category'
      ? {
          fact: derivation.fact,
          value: signalValue(derivation.value),
          rule: derivation.rule,
          ticketIds: derivation.ticket_ids,
          categories: {
            counts: Object.keys(derivation.category_counts)
              .sort()
              .map((category) => ({
                category,
                count: derivation.category_counts[category] as number,
              })),
            lookback: `${derivation.lookback.start} to ${derivation.lookback.end}`,
          },
        }
      : {
          fact: derivation.fact,
          value: signalValue(derivation.value),
          rule: derivation.rule,
          ticketIds: derivation.ticket_ids,
          categories: null,
        },
  );
}

export interface DissentView {
  position: Position;
  /** The policy whose resolution overruled this position, when one did. */
  overruledBy: string | null;
}

function samePosition(left: Position, right: Position): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function dissentViews(reconciliation: Reconciliation): DissentView[] {
  return reconciliation.dissent.map((position) => ({
    position,
    overruledBy:
      reconciliation.resolutions.find((resolution) =>
        resolution.dissent.some((dissent) => samePosition(dissent, position)),
      )?.policy_id ?? null,
  }));
}

export interface BriefView {
  identity: {
    customerId: string;
    sourceSystem: string;
    asOf: string;
    fingerprint: string;
    versions: { payload: number; rules: number; linker: string; policy: number };
  };
  risk: {
    band: Payload['band'];
    satisfiedRules: string[];
    worthiness: Reconciliation['worthiness'];
  };
  signals: {
    rows: SignalRow[];
    derivations: DerivationView[];
    escalationWindow: SupportEvidence['escalation_window'];
    ticketSpan: SupportEvidence['ticket_span'];
  };
  evidence: {
    tickets: SupportEvidence['tickets'];
    documents: Payload['document_evidence'];
    deals: Payload['commercial_evidence']['deals'];
    quotes: Payload['cited_spans'];
  };
  commercial: {
    activeDeals: { id: string; stage: string; probability: string; amount: string }[];
    exposure: string[];
    activeProjectCount: number;
  };
  conflicts: Reconciliation['conflicts'];
  resolutions: Reconciliation['resolutions'];
  dissent: DissentView[];
  policy: { quotes: Payload['cited_spans']; contractDocumentIds: string[] };
  backlogTicketIds: string[];
  actions: Position[];
  escalation: SupportEvidence['escalation_path'];
  narrative: string;
  technical: {
    briefId: string;
    assessmentId: string;
    status: string;
    policyVersion: number;
    templateVersion: string;
    payloadHash: string;
    citationCount: number;
  };
}

/** Every section of one brief, from its stored response and its version-1 payload. */
export function buildBriefView(response: BriefResponse, payload: Payload): BriefView {
  const { signals, reconciliation, support_evidence: support } = payload;
  return {
    identity: {
      customerId: payload.customer.id,
      sourceSystem: payload.scope.source_system,
      asOf: payload.scope.as_of,
      fingerprint: payload.scope.layer1_fingerprint,
      versions: {
        payload: payload.payload_version,
        rules: payload.versions.rules,
        linker: payload.versions.linker,
        policy: payload.versions.policy,
      },
    },
    risk: {
      band: payload.band,
      satisfiedRules: payload.satisfied_rules,
      worthiness: reconciliation.worthiness,
    },
    signals: {
      rows: signalRows(signals),
      derivations: derivationViews(support.derivations),
      escalationWindow: support.escalation_window,
      ticketSpan: support.ticket_span,
    },
    evidence: {
      tickets: support.tickets,
      documents: payload.document_evidence,
      deals: payload.commercial_evidence.deals,
      quotes: payload.cited_spans,
    },
    commercial: {
      activeDeals: signals.active_deals.map((deal) => ({
        id: deal.id,
        stage: deal.stage,
        probability: deal.probability,
        amount: formatMoney(deal.amount),
      })),
      exposure: exposureLines(signals.exposure_by_currency),
      activeProjectCount: signals.active_project_count,
    },
    conflicts: reconciliation.conflicts,
    resolutions: reconciliation.resolutions,
    dissent: dissentViews(reconciliation),
    policy: { quotes: payload.cited_spans, contractDocumentIds: signals.contract_document_ids },
    backlogTicketIds: support.backlog_ticket_ids,
    actions: reconciliation.resolved_positions,
    escalation: support.escalation_path,
    narrative: response.narrative,
    technical: {
      briefId: response.id,
      assessmentId: response.assessment_id,
      status: response.status,
      policyVersion: response.policy_version,
      templateVersion: response.template_version,
      payloadHash: response.payload_hash,
      citationCount: response.citations.length,
    },
  };
}
