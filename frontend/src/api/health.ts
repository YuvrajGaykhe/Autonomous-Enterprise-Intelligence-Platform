/** `GET /api/v1/health` (HUD, MEMORY). A 503 carries the same body, with the database unavailable. */

import { getJson, type RequestOptions } from './client';
import { healthResponse } from './schemas/operations';

export function fetchHealth(options: RequestOptions = {}) {
  return getJson('/api/v1/health', healthResponse, { ...options, acceptStatuses: [503] });
}
