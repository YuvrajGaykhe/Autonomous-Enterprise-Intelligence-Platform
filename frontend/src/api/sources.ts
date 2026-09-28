/** `GET /api/v1/sources` and `GET /api/v1/sources/{source}/health` (the roster's connectors). */

import { getJson, type RequestOptions } from './client';
import { sourceHealthResponse, sourceListResponse } from './schemas/operations';

export function fetchSources(options: RequestOptions = {}) {
  return getJson('/api/v1/sources', sourceListResponse, options);
}

export function fetchSourceHealth(source: string, options: RequestOptions = {}) {
  return getJson(
    `/api/v1/sources/${encodeURIComponent(source)}/health`,
    sourceHealthResponse,
    options,
  );
}
