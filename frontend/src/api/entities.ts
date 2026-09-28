/** `GET /api/v1/entities/{type}` for the seven canonical types. */

import { getJson, type RequestOptions } from './client';
import { fetchAllPages, type AllPages } from './pagination';
import { entityPages, type EntityRecord, type EntityType } from './schemas/entities';

function entityPath(type: EntityType, limit: number, offset: number, sourceSystem?: string) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (sourceSystem !== undefined) query.set('source_system', sourceSystem);
  return `/api/v1/entities/${type}?${query.toString()}`;
}

/** Every record of one type, optionally from one source system. */
export async function fetchEntities<T extends EntityType>(
  type: T,
  options: RequestOptions & { sourceSystem?: string } = {},
) {
  const { sourceSystem, ...request } = options;
  const pages = await fetchAllPages(
    (limit, offset) => entityPath(type, limit, offset, sourceSystem),
    entityPages[type],
    request,
  );
  // entityPages[T] parses exactly the records of T; TypeScript cannot correlate the two.
  return pages as AllPages<EntityRecord<T>>;
}

/** The number of records of one type: one request, which reads `total` only (MEMORY). */
export async function fetchEntityTotal(type: EntityType, options: RequestOptions = {}) {
  const result = await getJson(entityPath(type, 1, 0), entityPages[type], options);
  return { total: result.data.total, call: result.call };
}
