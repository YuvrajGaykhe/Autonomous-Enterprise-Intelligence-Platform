/**
 * Paging for every list route (spec §6.5): `limit=500` until `offset + items.length >= total`.
 *
 * No caller may assume that one page is everything, even though every list fits in one page today.
 */

import type { z } from 'zod';

import { getJson, type ApiCall, type RequestOptions } from './client';

export const PAGE_SIZE = 500;

interface Page {
  items: unknown[];
  total: number;
}

/** The item type of a page schema. */
export type ItemOf<S extends z.ZodType<Page>> = z.infer<S>['items'][number];

export interface AllPages<T> {
  items: T[];
  total: number;
  calls: ApiCall[];
}

/** Every page of a list route. `pathFor` builds the path for a limit and an offset. */
export async function fetchAllPages<S extends z.ZodType<Page>>(
  pathFor: (limit: number, offset: number) => string,
  schema: S,
  options: RequestOptions = {},
): Promise<AllPages<ItemOf<S>>> {
  const items: ItemOf<S>[] = [];
  const calls: ApiCall[] = [];
  let total = 0;
  do {
    const result = await getJson(pathFor(PAGE_SIZE, items.length), schema, options);
    const page: z.infer<S> = result.data;
    calls.push(result.call);
    total = page.total;
    items.push(...page.items);
    if (page.items.length === 0) break;
  } while (items.length < total);
  return { items, total, calls };
}
