/** Ingestion runs (connector panels) and the one ingestion write (R-F-6). */

import { getJson, postJson, type RequestOptions } from './client';
import { fetchAllPages } from './pagination';
import {
  errorListResponse,
  ingestionRunCreatedResponse,
  ingestionRunResponse,
  runListResponse,
} from './schemas/operations';

export function fetchRuns(options: RequestOptions = {}) {
  return fetchAllPages(
    (limit, offset) => `/api/v1/ingestion/runs?limit=${limit}&offset=${offset}`,
    runListResponse,
    options,
  );
}

export function fetchRun(runId: string, options: RequestOptions = {}) {
  return getJson(
    `/api/v1/ingestion/runs/${encodeURIComponent(runId)}`,
    ingestionRunResponse,
    options,
  );
}

export function fetchRunErrors(runId: string, options: RequestOptions = {}) {
  return fetchAllPages(
    (limit, offset) =>
      `/api/v1/ingestion/runs/${encodeURIComponent(runId)}/errors?limit=${limit}&offset=${offset}`,
    errorListResponse,
    options,
  );
}

/**
 * How many ingestion runs exist: one single-row request that reads `total` only. A run reads it
 * before its POST, and again after an outcome it cannot know (R-F-7).
 */
export async function countRuns(options: RequestOptions = {}) {
  const result = await getJson('/api/v1/ingestion/runs?limit=1&offset=0', runListResponse, options);
  return { total: result.data.total, call: result.call };
}

/** Start an ingestion of one source. The body is `{"source": …}` only (R-F-6). */
export function startIngestion(source: string, options: RequestOptions = {}) {
  return postJson('/api/v1/ingestion/runs', { source }, ingestionRunCreatedResponse, options);
}
