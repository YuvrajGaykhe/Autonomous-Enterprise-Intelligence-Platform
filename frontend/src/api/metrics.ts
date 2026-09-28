/** `GET /api/v1/metrics/ingestion` (MEMORY). */

import { getJson, type RequestOptions } from './client';
import { ingestionMetricsResponse } from './schemas/operations';

export function fetchIngestionMetrics(options: RequestOptions = {}) {
  return getJson('/api/v1/metrics/ingestion', ingestionMetricsResponse, options);
}
