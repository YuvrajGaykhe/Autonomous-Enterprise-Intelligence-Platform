/**
 * Primitive schemas shared by every response (spec §6.2, §6.4, §7.7, §7.8).
 *
 * Every object schema in this folder is strict: an unknown key is a contract
 * failure, never silently ignored. Integers are integers, so a float where the
 * backend promises an int fails to parse.
 */

import { z } from 'zod';

export const integer = z.number().int();
export const count = z.number().int().nonnegative();
export const uuid = z.uuid();
/** A calendar date, kept as the string it is and never passed through `Date` (§7.8). */
export const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
export const isoDateTime = z.iso.datetime({ offset: true });
/** A decimal amount, kept as its JSON string and never parsed to a float (§7.7). */
export const decimalText = z.string().regex(/^-?\d+(?:\.\d+)?$/);
export const sha256Hex = z.string().regex(/^[0-9a-f]{64}$/);

/** One limit/offset page of a list route. */
export function page<T extends z.ZodType>(item: T) {
  return z.strictObject({
    items: z.array(item),
    total: count,
    limit: count,
    offset: count,
  });
}
