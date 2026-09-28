/**
 * Risk bands (spec §7.1; DERIVED from `app/intelligence/contract.py` `RiskBand`, D-F-2).
 *
 * The order is NONE < WATCH < ELEVATED < CRITICAL. A band is always shown as its word with an
 * icon, never as a number: nothing here turns a band into a figure for display.
 */

import type { RiskBand } from '@/api/schemas/briefPayloadV1';

/** Every band, lowest first. */
export const BANDS = [
  'NONE',
  'WATCH',
  'ELEVATED',
  'CRITICAL',
] as const satisfies readonly RiskBand[];

/** Every band, highest first: the order band counts are listed in. */
export const BANDS_HIGHEST_FIRST = [...BANDS].reverse() as readonly RiskBand[];

export interface BandCount {
  band: RiskBand;
  count: number;
}

/** How many items carry each band, highest band first, with zero counts omitted. */
export function bandCounts(items: readonly { band: RiskBand }[]): BandCount[] {
  return BANDS_HIGHEST_FIRST.map((band) => ({
    band,
    count: items.filter((item) => item.band === band).length,
  })).filter((entry) => entry.count > 0);
}

/** `1 CRITICAL · 2 WATCH · 47 NONE`: customer counts per band, never a score. */
export function describeBandCounts(counts: readonly BandCount[]): string {
  return counts.map((entry) => `${entry.count} ${entry.band}`).join(' · ');
}
