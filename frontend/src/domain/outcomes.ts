/**
 * What a failed write means, and what the page does next (spec §7.6, R-F-7; DERIVED from
 * `app/decisions/approval.py`, `app/api/errors.py` and `app/api/v1/risk.py`).
 *
 * Every POST owns one transaction and rolls back on failure, so an API error means nothing was
 * written. Only a request that never produced an API answer has an unknown outcome, and the page
 * re-reads before it offers a retry. No POST is ever retried automatically.
 */

import { ApiError, NetworkError, isApiFailure, type ApiFailure } from '@/api/client';

/** The fixed messages of §7.6's table. */
export const OUTCOME_MESSAGES = {
  staleHead: 'Someone recorded a decision on this brief meanwhile.',
  defect:
    'The API refused this decision because this page sent an inconsistent request. Nothing was written.',
  briefChanged: 'This brief changed since you opened it.',
  payloadMismatch:
    "This brief's stored payload no longer matches its hash, so decisions on it are refused.",
  scopeUnresolved: 'No support ticket exists to resolve the date from. Choose an explicit date.',
  nothingWritten: 'Nothing was written.',
  invalid: 'The API refused the request as invalid. Nothing was written.',
} as const;

const STALE_HEAD_REASONS = new Set([
  'SUPERSEDES_REQUIRED',
  'PREDECESSOR_NOT_HEAD',
  'CONCURRENT_DECISION',
]);

export type WriteFailure =
  /** 409 DECISION_CONFLICT, the chain moved: reload it and keep the form. */
  | { kind: 'stale-head'; error: ApiError }
  /** 409 DECISION_CONFLICT PREDECESSOR_NOT_ON_BRIEF: a defect; reload the chain. */
  | { kind: 'defect'; error: ApiError }
  /** 409 PAYLOAD_HASH_CONFLICT REQUEST_HASH_MISMATCH: reload the brief; keep the note. */
  | { kind: 'brief-changed'; error: ApiError }
  /** 409 PAYLOAD_HASH_CONFLICT STORED_PAYLOAD_MISMATCH: decisions on this brief are refused. */
  | { kind: 'payload-mismatch'; error: ApiError }
  /** 422 SCOPE_UNRESOLVED: Auto found no ticket to take the date from. */
  | { kind: 'scope-unresolved'; error: ApiError }
  /** 422 INVALID_REQUEST: the field messages. */
  | { kind: 'invalid'; error: ApiError; fields: string[] }
  /** 404: the brief or the assessment does not exist. */
  | { kind: 'not-found'; error: ApiError }
  /** Any other API error: nothing was written; a retry may be offered. */
  | { kind: 'nothing-written'; error: ApiError }
  /** No API answer: re-read before offering a retry. */
  | { kind: 'unknown'; error: NetworkError }
  /** The API answered in a shape this frontend cannot read, or the page failed. */
  | { kind: 'unreadable'; error: unknown };

/** `loc: message` for each entry of a validation error's details. */
export function fieldMessages(error: ApiError): string[] {
  const details = error.details;
  if (!Array.isArray(details)) return [];
  return details.map((detail) => {
    const location = Array.isArray(detail.loc) ? detail.loc.map(String).join('.') : '';
    const message = typeof detail.message === 'string' ? detail.message : 'invalid';
    return location === '' ? message : `${location}: ${message}`;
  });
}

function classifyApiError(error: ApiError): WriteFailure {
  if (error.code === 'DECISION_CONFLICT') {
    return STALE_HEAD_REASONS.has(error.reason ?? '')
      ? { kind: 'stale-head', error }
      : { kind: 'defect', error };
  }
  if (error.code === 'PAYLOAD_HASH_CONFLICT') {
    return error.reason === 'STORED_PAYLOAD_MISMATCH'
      ? { kind: 'payload-mismatch', error }
      : { kind: 'brief-changed', error };
  }
  if (error.code === 'SCOPE_UNRESOLVED') return { kind: 'scope-unresolved', error };
  if (error.code === 'INVALID_REQUEST')
    return { kind: 'invalid', error, fields: fieldMessages(error) };
  if (error.status === 404) return { kind: 'not-found', error };
  return { kind: 'nothing-written', error };
}

/** Classify what a POST's failure means (§7.6). */
export function classifyWriteFailure(error: unknown): WriteFailure {
  if (!isApiFailure(error)) return { kind: 'unreadable', error };
  const failure: ApiFailure = error;
  if (failure instanceof ApiError) return classifyApiError(failure);
  if (failure instanceof NetworkError) return { kind: 'unknown', error: failure };
  return { kind: 'unreadable', error: failure };
}

/** The request id to show with a failure, when one arrived. */
export function failureRequestId(failure: WriteFailure): string | null {
  const error = failure.error;
  return isApiFailure(error) ? error.requestId : null;
}
