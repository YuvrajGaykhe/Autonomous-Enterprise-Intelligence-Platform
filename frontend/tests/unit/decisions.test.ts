/**
 * The decision chain, the decision request and what a failed write means (spec §7.5, §7.6,
 * R-F-7), on the recorded decision flow.
 */

import { describe, expect, it } from 'vitest';

import { ApiError, ContractError, NetworkError, type ApiCall } from '@/api/client';
import type { DecisionRequest, DecisionResponse } from '@/api/schemas/risk';
import {
  MAX_ACTOR_CODE_POINTS,
  MAX_NOTE_CODE_POINTS,
  buildDecisionRequest,
  chainEntries,
  chainHead,
  codePointLength,
  decisionLanded,
  ordinalMark,
} from '@/domain/decisionChain';
import {
  OUTCOME_MESSAGES,
  classifyWriteFailure,
  failureRequestId,
  fieldMessages,
} from '@/domain/outcomes';

import { decisionFlow, recordedBriefs, type RecordedExchange } from '../support/fixtures';

const flow = decisionFlow();
const chainExchange = flow.find(
  (item) => item.method === 'GET' && item.path.endsWith('/decisions') && item.status === 200,
) as RecordedExchange;
const chain = (chainExchange.body as { items: DecisionResponse[] }).items;
const [first, second] = chain as [DecisionResponse, DecisionResponse];
const payloadHash = (recordedBriefs()[0]?.body as { payload_hash: string }).payload_hash;

const call: ApiCall = { method: 'POST', path: '/x', status: 409, durationMs: 1, requestId: 'r1' };

/** The recorded refusal whose `details.reason` (or code) is `reason`, as an ApiError. */
function refusal(reason: string): ApiError {
  const exchange = flow.find((item) => {
    const error = (item.body as { error?: { code: string; details: unknown } }).error;
    if (error === undefined) return false;
    const details = error.details as { reason?: string } | null;
    return details?.reason === reason || error.code === reason;
  }) as RecordedExchange;
  const body = (exchange.body as { error: ConstructorParameters<typeof ApiError>[1] }).error;
  return new ApiError(exchange.status, body, body.request_id, { ...call, status: exchange.status });
}

describe('the decision chain (§7.5)', () => {
  it('numbers the recorded chain first to head, the second superseding the first', () => {
    const entries = chainEntries(chain);
    expect(entries.map((entry) => [entry.mark, entry.decision.decision])).toEqual([
      ['①', 'APPROVED'],
      ['②', 'REJECTED'],
    ]);
    expect(entries[0]?.supersedes).toBeNull();
    expect(entries[1]?.supersedes).toEqual({ id: first.id, mark: '①' });
    expect(chainHead(chain)).toBe(second);
    expect(chainHead([])).toBeNull();
  });

  it('shows no supersede link for a predecessor outside the chain', () => {
    const [entry] = chainEntries([
      { ...second, supersedes_id: '00000000-0000-4000-8000-000000000001' },
    ]);
    expect(entry?.supersedes).toBeNull();
  });

  it('marks ① to ⑳, then (21) onwards', () => {
    expect(ordinalMark(1)).toBe('①');
    expect(ordinalMark(20)).toBe('⑳');
    expect(ordinalMark(21)).toBe('(21)');
  });
});

describe('the decision request (§7.5)', () => {
  const form = { actor: '  Owner  ', decision: 'APPROVED' as const, note: '  ok  ' };

  it('supersedes nothing on an empty chain, and the head otherwise', () => {
    expect(buildDecisionRequest(form, payloadHash, [])).toEqual({
      ok: true,
      request: {
        actor: 'Owner',
        decision: 'APPROVED',
        note: 'ok',
        payload_hash: payloadHash,
        supersedes_id: null,
      },
    });
    const next = buildDecisionRequest({ ...form, decision: 'REJECTED' }, payloadHash, chain);
    expect(next).toMatchObject({ ok: true, request: { supersedes_id: second.id } });
  });

  it('sends an empty note as null', () => {
    expect(buildDecisionRequest({ ...form, note: '   ' }, payloadHash, [])).toMatchObject({
      ok: true,
      request: { note: null },
    });
  });

  it('refuses a missing decision, a blank name, and lengths past the API limits', () => {
    expect(buildDecisionRequest({ actor: ' ', decision: null, note: '' }, payloadHash, [])).toEqual(
      {
        ok: false,
        problems: ['Choose Approve or Reject.', 'Enter your name.'],
      },
    );
    const long = buildDecisionRequest(
      {
        actor: 'a'.repeat(MAX_ACTOR_CODE_POINTS + 1),
        decision: 'APPROVED',
        note: 'n'.repeat(MAX_NOTE_CODE_POINTS + 1),
      },
      payloadHash,
      [],
    );
    expect(long).toEqual({
      ok: false,
      problems: [
        'Your name is longer than 255 characters.',
        'The note is longer than 2000 characters.',
      ],
    });
  });

  it('counts the limits in code points, as the API does', () => {
    const emoji = '😀'.repeat(MAX_ACTOR_CODE_POINTS);
    expect(emoji.length).toBe(MAX_ACTOR_CODE_POINTS * 2);
    expect(codePointLength(emoji)).toBe(MAX_ACTOR_CODE_POINTS);
    expect(buildDecisionRequest({ ...form, actor: emoji }, payloadHash, []).ok).toBe(true);
  });

  it('finds a sent decision in a re-read chain, and nothing else (R-F-7)', () => {
    const sent: DecisionRequest = {
      actor: second.actor,
      decision: second.decision,
      note: second.note,
      payload_hash: second.payload_hash,
      supersedes_id: second.supersedes_id,
    };
    expect(decisionLanded(chain, sent)).toBe(second);
    expect(decisionLanded(chain, { ...sent, note: 'different' })).toBeNull();
    expect(decisionLanded(chain, { ...sent, supersedes_id: null })).toBeNull();
    expect(decisionLanded(chain, { ...sent, actor: 'someone else' })).toBeNull();
    expect(decisionLanded(chain, { ...sent, decision: 'APPROVED' })).toBeNull();
    expect(decisionLanded(chain, { ...sent, payload_hash: '0'.repeat(64) })).toBeNull();
    expect(decisionLanded([], sent)).toBeNull();
  });
});

describe('what a failed write means (§7.6)', () => {
  it.each([
    ['SUPERSEDES_REQUIRED', 'stale-head'],
    ['PREDECESSOR_NOT_HEAD', 'stale-head'],
    ['PREDECESSOR_NOT_ON_BRIEF', 'defect'],
    ['REQUEST_HASH_MISMATCH', 'brief-changed'],
    ['INVALID_REQUEST', 'invalid'],
    ['BRIEF_NOT_FOUND', 'not-found'],
  ])('reads the recorded %s refusal as %s', (reason, kind) => {
    const failure = classifyWriteFailure(refusal(reason));
    expect(failure.kind).toBe(kind);
    expect(failureRequestId(failure)).toMatch(/^[0-9a-f]{32}$/);
  });

  it('reads CONCURRENT_DECISION as a moved head and STORED_PAYLOAD_MISMATCH as refused', () => {
    const concurrent = refusal('SUPERSEDES_REQUIRED');
    const moved = new ApiError(
      409,
      {
        code: concurrent.code,
        message: concurrent.message,
        details: { reason: 'CONCURRENT_DECISION' },
        request_id: 'r2',
      },
      'r2',
      call,
    );
    expect(classifyWriteFailure(moved).kind).toBe('stale-head');
    const hash = refusal('REQUEST_HASH_MISMATCH');
    const stored = new ApiError(
      409,
      {
        code: hash.code,
        message: hash.message,
        details: { reason: 'STORED_PAYLOAD_MISMATCH' },
        request_id: 'r3',
      },
      'r3',
      call,
    );
    expect(classifyWriteFailure(stored).kind).toBe('payload-mismatch');
  });

  it('reads a DECISION_CONFLICT without a reason as a defect', () => {
    const bare = new ApiError(
      409,
      { code: 'DECISION_CONFLICT', message: 'm', details: null, request_id: 'r' },
      'r',
      call,
    );
    expect(classifyWriteFailure(bare).kind).toBe('defect');
  });

  it('reads SCOPE_UNRESOLVED, a 500, a timeout, a bad body and a thrown value', () => {
    const scope = new ApiError(
      422,
      { code: 'SCOPE_UNRESOLVED', message: 'm', details: null, request_id: 'r' },
      'r',
      call,
    );
    expect(classifyWriteFailure(scope).kind).toBe('scope-unresolved');
    const internal = new ApiError(
      500,
      { code: 'INTERNAL_ERROR', message: 'm', details: null, request_id: 'r5' },
      'r5',
      call,
    );
    expect(classifyWriteFailure(internal).kind).toBe('nothing-written');
    const timeout = classifyWriteFailure(new NetworkError('The request timed out.', true, call));
    expect(timeout.kind).toBe('unknown');
    expect(failureRequestId(timeout)).toBe('r1');
    expect(classifyWriteFailure(new ContractError('bad', [], call)).kind).toBe('unreadable');
    const thrown = classifyWriteFailure(new Error('page'));
    expect(thrown.kind).toBe('unreadable');
    expect(failureRequestId(thrown)).toBeNull();
  });

  it('lists the recorded validation messages by location', () => {
    expect(fieldMessages(refusal('INVALID_REQUEST'))).toEqual([
      'body.actor: String should have at least 1 character',
    ]);
    const odd = new ApiError(
      422,
      {
        code: 'INVALID_REQUEST',
        message: 'm',
        details: [{ message: 'no location' }, { loc: ['query'] }],
        request_id: 'r',
      },
      'r',
      call,
    );
    expect(fieldMessages(odd)).toEqual(['no location', 'query: invalid']);
    expect(fieldMessages(refusal('BRIEF_NOT_FOUND'))).toEqual([]);
  });

  it('has a message for every row of §7.6', () => {
    expect(Object.keys(OUTCOME_MESSAGES)).toEqual([
      'staleHead',
      'defect',
      'briefChanged',
      'payloadMismatch',
      'scopeUnresolved',
      'nothingWritten',
      'invalid',
    ]);
  });
});
