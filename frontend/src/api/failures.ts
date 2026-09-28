/**
 * What the error state shows for a failure (spec §8.7): the message, the code and the request id.
 */

import { ApiError, ContractError, NetworkError } from './client';

export interface FailureView {
  message: string;
  code: string;
  requestId: string | null;
  issues: readonly string[];
}

export function describeFailure(error: unknown): FailureView {
  if (error instanceof ApiError) {
    return { message: error.message, code: error.code, requestId: error.requestId, issues: [] };
  }
  if (error instanceof NetworkError) {
    return {
      message: error.message,
      code: error.timedOut ? 'TIMEOUT' : 'NETWORK_ERROR',
      requestId: error.requestId,
      issues: [],
    };
  }
  if (error instanceof ContractError) {
    return {
      message: error.message,
      code: 'CONTRACT_ERROR',
      requestId: error.requestId,
      issues: error.issues,
    };
  }
  return {
    message: 'This page failed unexpectedly.',
    code: 'UNEXPECTED',
    requestId: null,
    issues: [],
  };
}
