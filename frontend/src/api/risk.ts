/**
 * Risk assessments, briefs and decisions (spec §6.3, §6.4, §6.6, §7.5).
 *
 * Two of the three writes live here: `runAssessment` and `recordDecision`. Neither is ever
 * retried automatically (R-F-7).
 */

import {
  ContractError,
  TIMEOUTS,
  describeIssues,
  getJson,
  postJson,
  type ApiResult,
  type RequestOptions,
} from './client';
import { fetchAllPages } from './pagination';
import { PAYLOAD_VERSION, briefPayloadV1, type BriefPayloadV1 } from './schemas/briefPayloadV1';
import {
  assessmentDetailResponse,
  assessmentListResponse,
  assessmentRunResponse,
  briefResponse,
  decisionHistoryResponse,
  decisionResponse,
  type BriefResponse,
  type DecisionRequest,
} from './schemas/risk';

/** The only source system VS-01 assesses. `customer_source_id` is never sent (§6.3). */
export const SOURCE_SYSTEM = 'csv_demo';

/**
 * Assess every customer in scope at `asOf`, or at the latest ticket's date when `asOf` is
 * null (D-F-14). 201 means something was created; 200 means every result already existed.
 */
export function runAssessment(asOf: string | null, options: RequestOptions = {}) {
  return postJson(
    '/api/v1/risk/assessments',
    { as_of: asOf, source_system: SOURCE_SYSTEM },
    assessmentRunResponse,
    { timeoutMs: TIMEOUTS.assessment, ...options },
  );
}

/** Every assessment at one `as_of`, in the API's order (§7.2). */
export function fetchAssessments(asOf: string, options: RequestOptions = {}) {
  return fetchAllPages(
    (limit, offset) =>
      `/api/v1/risk/assessments?as_of=${encodeURIComponent(asOf)}&limit=${limit}&offset=${offset}`,
    assessmentListResponse,
    options,
  );
}

export function fetchAssessment(assessmentId: string, options: RequestOptions = {}) {
  return getJson(
    `/api/v1/risk/assessments/${encodeURIComponent(assessmentId)}`,
    assessmentDetailResponse,
    options,
  );
}

/** A brief whose payload this frontend can read, or one it must not render (§6.4). */
export type Brief =
  | { supported: true; response: BriefResponse; payload: BriefPayloadV1 }
  | { supported: false; response: BriefResponse; payloadVersion: number };

/** Parse a brief's payload by its version. A version-1 payload that fails its schema is a ContractError. */
export function parseBrief(result: ApiResult<BriefResponse>): Brief {
  const response = result.data;
  if (response.payload.payload_version !== PAYLOAD_VERSION) {
    return { supported: false, response, payloadVersion: response.payload.payload_version };
  }
  const parsed = briefPayloadV1.safeParse(response.payload);
  if (!parsed.success) {
    throw new ContractError(
      'The brief payload did not match payload version 1.',
      describeIssues(parsed.error),
      result.call,
    );
  }
  return { supported: true, response, payload: parsed.data };
}

export async function fetchBrief(briefId: string, options: RequestOptions = {}) {
  const result = await getJson(
    `/api/v1/risk/briefs/${encodeURIComponent(briefId)}`,
    briefResponse,
    options,
  );
  return { brief: parseBrief(result), call: result.call };
}

/** Record one decision. `supersedes_id` must name the chain's head, or be null for the first. */
export function recordDecision(
  briefId: string,
  request: DecisionRequest,
  options: RequestOptions = {},
) {
  return postJson(
    `/api/v1/risk/briefs/${encodeURIComponent(briefId)}/decision`,
    request,
    decisionResponse,
    options,
  );
}

/** The brief's decisions, first to head (§7.5). */
export function fetchDecisions(briefId: string, options: RequestOptions = {}) {
  return getJson(
    `/api/v1/risk/briefs/${encodeURIComponent(briefId)}/decisions`,
    decisionHistoryResponse,
    options,
  );
}
