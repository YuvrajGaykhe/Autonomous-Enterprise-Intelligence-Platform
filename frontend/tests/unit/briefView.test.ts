/**
 * The brief view model, cited text and money (spec §7.3, §7.4, §7.7), checked against the
 * recorded briefs and the golden CUST-007 brief, which is read and never written.
 */

import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { briefPayloadV1, type BriefPayloadV1 } from '@/api/schemas/briefPayloadV1';
import type { Document } from '@/api/schemas/entities';
import type { BriefResponse } from '@/api/schemas/risk';
import {
  RISK_SIGNALS,
  buildBriefView,
  derivationViews,
  dissentViews,
  signalRows,
  signalValue,
} from '@/domain/briefView';
import { exposureLines, formatMoney, groupDigits } from '@/domain/money';
import { findRecord } from '@/domain/records';
import {
  MAX_QUOTE_CODE_POINTS,
  citableText,
  highlight,
  quote,
  sliceCodePoints,
  spanFits,
} from '@/domain/spans';

import { REPO_ROOT, recordedBriefs, recordedEntities } from '../support/fixtures';

const golden = readFileSync(`${REPO_ROOT}tests/golden/vs01_cust007_brief.txt`, 'utf8');
const [cust007, cust025, cust036] = recordedBriefs().map((exchange) => {
  const response = exchange.body as BriefResponse;
  return { response, payload: briefPayloadV1.parse(response.payload) };
}) as [Brief, Brief, Brief];
const documents = recordedEntities<{ items: Document[] }>('documents').items;

interface Brief {
  response: BriefResponse;
  payload: BriefPayloadV1;
}

/** The golden brief's lines of one numbered section. */
function goldenSection(number: number): string[] {
  const start = golden.indexOf(`\n${number}. `);
  const end = golden.indexOf(`\n${number + 1}. `, start + 1);
  return golden.slice(start, end === -1 ? undefined : end).split('\n');
}

describe('the brief view (§7.3)', () => {
  const view = buildBriefView(cust007.response, cust007.payload);

  it('maps identity, risk and technical fields to their payload and response paths', () => {
    expect(view.identity).toEqual({
      customerId: 'CUST-007',
      sourceSystem: 'csv_demo',
      asOf: '2026-09-18',
      fingerprint: '1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00',
      versions: { payload: 1, rules: 1, linker: '1', policy: 1 },
    });
    expect(view.risk.band).toBe('CRITICAL');
    expect(view.risk.worthiness.executive_worthy).toBe(true);
    expect(view.technical).toMatchObject({
      status: 'DRAFT',
      policyVersion: 1,
      templateVersion: '1',
      payloadHash: 'e93c29cfb6094284d7ea6fe84bf966ad0b40995fccdc4e2a671b502a7f16c946',
      citationCount: cust007.response.citations.length,
    });
    expect(view.narrative).toBe(golden);
  });

  it('writes every S1–S15 risk signal exactly as the golden brief does', () => {
    const lines = goldenSection(2);
    expect(RISK_SIGNALS).toHaveLength(14);
    for (const row of view.signals.rows) {
      expect(lines).toContain(`- ${row.id} ${row.key}: ${row.value}`);
    }
  });

  it('writes a null signal as none, and booleans and numbers as themselves', () => {
    expect(signalValue(null)).toBe('none');
    expect(signalValue(true)).toBe('true');
    expect(signalValue(0)).toBe('0');
    expect(signalValue('performance')).toBe('performance');
    const quiet = signalRows({ ...cust007.payload.signals, days_since_last_ticket: null });
    expect(quiet.find((row) => row.key === 'days_since_last_ticket')?.value).toBe('none');
  });

  it('states each derivation with its tickets, and the category counts sorted by name', () => {
    const lines = goldenSection(2).join('\n');
    for (const derivation of view.signals.derivations) {
      expect(lines).toContain(
        `- ${derivation.fact} = ${derivation.value}, counting ${derivation.ticketIds.join(', ')}`,
      );
      expect(lines).toContain(`rule: ${derivation.rule}`);
    }
    const category = view.signals.derivations.at(-1)?.categories;
    expect(category?.counts).toEqual([
      { category: 'billing', count: 1 },
      { category: 'integration', count: 1 },
      { category: 'performance', count: 3 },
    ]);
    expect(lines).toContain(`lookback ${category?.lookback}`);
    expect(view.signals.derivations.slice(0, 4).every((item) => item.categories === null)).toBe(
      true,
    );
  });

  it('writes a null dominant category as none', () => {
    const derivations = cust007.payload.support_evidence.derivations;
    const [a, b, c, d, category] = derivations;
    const views = derivationViews([a, b, c, d, { ...category, value: null, category_counts: {} }]);
    expect(views[4]).toMatchObject({ value: 'none', categories: { counts: [] } });
  });

  it('states money per currency, comma-grouped and never rounded, with no cross-currency total', () => {
    expect(view.commercial.activeDeals).toEqual([
      { id: 'DEAL-001', stage: 'negotiation', probability: '90', amount: 'USD 5,361.44' },
    ]);
    expect(view.commercial.exposure).toEqual(['USD 5,361.44']);
    expect(goldenSection(4)).toContain('- USD 5,361.44');
    expect(
      exposureLines({
        USD: { amount: '10', currency: 'USD' },
        EUR: { amount: '1234567.5', currency: 'EUR' },
      }),
    ).toEqual(['EUR 1,234,567.5', 'USD 10']);
  });

  it('names the policy that overruled each dissenting position', () => {
    expect(view.dissent).toHaveLength(1);
    expect(view.dissent[0]?.overruledBy).toBe('CONF-001');
    expect(goldenSection(6).join('\n')).toContain(
      `Overruled by CONF-001: SALES ADVANCE ACCELERATE_DEAL_CLOSE on DEAL-001`,
    );
    const orphan = { ...cust007.payload.reconciliation, resolutions: [] };
    expect(dissentViews(orphan)[0]?.overruledBy).toBeNull();
  });

  it('keeps the recommended actions in resolved order, and the escalation path as stated', () => {
    expect(view.actions.map((action) => action.proposed_action)).toEqual([
      'ASSIGN_DEDICATED_SUPPORT_OWNER',
      'ESCALATE_TO_ACCOUNT_OWNER_PER_SLA',
      'SCHEDULE_EXECUTIVE_SPONSOR_CALL',
      'PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED',
      'REVIEW_INVOICE_DISPUTE',
    ]);
    expect(view.escalation.account_owner?.id).toBe('EMP-007');
    expect(view.policy.contractDocumentIds).toEqual(['DOC-006']);
    expect(view.backlogTicketIds).toEqual([]);
  });

  it('builds the no-conflict briefs with empty conflict, dissent and deal sections', () => {
    for (const brief of [cust025, cust036]) {
      const other = buildBriefView(brief.response, brief.payload);
      expect(other.conflicts).toEqual([]);
      expect(other.resolutions).toEqual([]);
      expect(other.dissent).toEqual([]);
      expect(other.evidence.documents).toEqual([]);
    }
    expect(buildBriefView(cust036.response, cust036.payload).actions).toEqual([]);
  });
});

describe('cited text (§7.4)', () => {
  const section7 = goldenSection(7).join('\n');

  it("quotes CUST-007's three cited spans exactly as the golden brief's section 7", () => {
    const spans = cust007.payload.cited_spans;
    expect(spans).toHaveLength(3);
    for (const span of spans) {
      const document = findRecord(documents, 'csv_demo', span.citation.document_id);
      expect(document).not.toBeNull();
      const text = citableText(document as Document);
      const cited = quote(text, span.citation.start, span.citation.end);
      expect(cited.truncated).toBe(false);
      expect(section7).toContain(
        `- ${span.target}, ${span.citation.document_id} [${span.citation.start}, ${span.citation.end}): "${cited.text}"`,
      );
    }
  });

  it('joins title and body with a newline, a null part counting as empty', () => {
    expect(citableText({ title: 'T', body_text: 'B' })).toBe('T\nB');
    expect(citableText({ title: null, body_text: null })).toBe('\n');
  });

  it('slices by code points, not UTF-16 units', () => {
    const text = 'a😀b€c';
    expect(text.length).toBe(6);
    expect(sliceCodePoints(text, 1, 3)).toBe('😀b');
    expect(text.slice(1, 3)).not.toBe('😀b');
    expect(highlight(text, 1, 2)).toEqual({ before: 'a', span: '😀', after: 'b€c' });
  });

  it('checks that a span is non-empty and inside the text', () => {
    expect(spanFits('abc', 0, 3)).toBe(true);
    expect(spanFits('abc', 1, 1)).toBe(false);
    expect(spanFits('abc', -1, 2)).toBe(false);
    expect(spanFits('a😀', 1, 3)).toBe(false);
  });

  it('caps a quote at 500 code points and marks it truncated', () => {
    const text = '😀'.repeat(MAX_QUOTE_CODE_POINTS + 5);
    const capped = quote(text, 0, MAX_QUOTE_CODE_POINTS + 5);
    expect(Array.from(capped.text)).toHaveLength(MAX_QUOTE_CODE_POINTS);
    expect(capped.truncated).toBe(true);
    expect(quote(text, 0, MAX_QUOTE_CODE_POINTS)).toMatchObject({ truncated: false });
  });
});

describe('money (§7.7)', () => {
  it.each([
    ['0', '0'],
    ['999', '999'],
    ['1000', '1,000'],
    ['5361.44', '5,361.44'],
    ['1234567.500', '1,234,567.500'],
    ['-1234.5', '-1,234.5'],
  ])('groups %s as %s, keeping the stated scale', (amount, grouped) => {
    expect(groupDigits(amount)).toBe(grouped);
  });

  it('refuses anything that is not a decimal string', () => {
    expect(() => groupDigits('1e5')).toThrow(/not a decimal amount/);
    expect(() => groupDigits('')).toThrow(/not a decimal amount/);
  });

  it('writes the currency, a space, then the amount', () => {
    expect(formatMoney({ amount: '5361.44', currency: 'USD' })).toBe('USD 5,361.44');
  });
});
