import { describe, expect, it } from 'vitest';

import { ApiError, ContractError, NetworkError, type ApiCall } from '@/api/client';
import { describeFailure } from '@/api/failures';
import { COPY, fill } from '@/copy';
import {
  DEFAULT_AS_OF,
  DEFAULT_AS_OF_DATE,
  formatAsOf,
  isCalendarDate,
  parseAsOf,
  requestAsOf,
} from '@/domain/asOf';

describe('as_of', () => {
  it('defaults to the explicit date 2026-09-18 (D-F-14)', () => {
    expect(DEFAULT_AS_OF).toEqual({ kind: 'date', date: '2026-09-18' });
    expect(parseAsOf(null)).toEqual(DEFAULT_AS_OF);
  });

  it.each(['2026-02-29', '2026-13-01', '2026-00-10', '2026-04-31', '26-09-18', 'yesterday', ''])(
    'reads the unreadable value %j as the default',
    (value) => {
      expect(parseAsOf(value)).toEqual(DEFAULT_AS_OF);
    },
  );

  it('keeps a real calendar date as the string it is', () => {
    expect(parseAsOf('2024-02-29')).toEqual({ kind: 'date', date: '2024-02-29' });
    expect(isCalendarDate('2026-12-31')).toBe(true);
  });

  it('reads auto as the Auto choice, which sends a null as_of', () => {
    const auto = parseAsOf('auto');
    expect(auto).toEqual({ kind: 'auto' });
    expect(formatAsOf(auto)).toBe('auto');
    expect(requestAsOf(auto)).toBeNull();
  });

  it('writes and sends a date as itself', () => {
    expect(formatAsOf(DEFAULT_AS_OF)).toBe(DEFAULT_AS_OF_DATE);
    expect(requestAsOf(DEFAULT_AS_OF)).toBe(DEFAULT_AS_OF_DATE);
  });
});

describe('describeFailure', () => {
  const call: ApiCall = { method: 'GET', path: '/x', status: 502, durationMs: 1, requestId: 'r1' };

  it('shows an API error with its own code and request id', () => {
    const error = new ApiError(
      404,
      {
        code: 'BRIEF_NOT_FOUND',
        message: 'risk brief does not exist',
        details: null,
        request_id: 'r2',
      },
      'r2',
      call,
    );
    expect(describeFailure(error)).toEqual({
      message: 'risk brief does not exist',
      code: 'BRIEF_NOT_FOUND',
      requestId: 'r2',
      issues: [],
    });
  });

  it('names a timeout and a network failure apart', () => {
    expect(describeFailure(new NetworkError('t', true, call)).code).toBe('TIMEOUT');
    expect(describeFailure(new NetworkError('n', false, call))).toMatchObject({
      code: 'NETWORK_ERROR',
      requestId: 'r1',
    });
  });

  it('carries a contract failure issues', () => {
    expect(describeFailure(new ContractError('c', ['a: b'], call))).toMatchObject({
      code: 'CONTRACT_ERROR',
      issues: ['a: b'],
    });
  });

  it('has a generic view for anything else', () => {
    expect(describeFailure(new Error('boom'))).toEqual({
      message: 'This page failed unexpectedly.',
      code: 'UNEXPECTED',
      requestId: null,
      issues: [],
    });
  });
});

describe('fill', () => {
  it('substitutes every named marker and leaves an unknown one as it is', () => {
    expect(fill(COPY.replayBanner, { date: '2026-09-18' })).toBe(
      'Replay of recorded results · as_of 2026-09-18',
    );
    expect(fill(COPY.lockedRoom, { n: 2 })).toBe('Opens with VS-02');
    expect(fill('{known} {unknown}', { known: 'x' })).toBe('x {unknown}');
  });
});
