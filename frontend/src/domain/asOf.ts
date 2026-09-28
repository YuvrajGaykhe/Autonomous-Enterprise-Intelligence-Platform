/**
 * The HUD's `as_of` choice (D-F-14, spec §8.1, §8.2).
 *
 * The default is the explicit date 2026-09-18. "Auto (latest ticket)" asks the API to resolve
 * the date itself, so a run sends `as_of: null`. In the URL the choice is `as_of=YYYY-MM-DD` or
 * `as_of=auto`. A calendar date stays the string it is: it is validated through UTC parts only
 * and never through a local-time `Date` (§7.8).
 */

export const DEFAULT_AS_OF_DATE = '2026-09-18';
export const AUTO = 'auto';

export type AsOf = { kind: 'date'; date: string } | { kind: 'auto' };

export const DEFAULT_AS_OF: AsOf = { kind: 'date', date: DEFAULT_AS_OF_DATE };

const CALENDAR_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Whether `value` is a real `YYYY-MM-DD` calendar date. */
export function isCalendarDate(value: string): boolean {
  const match = CALENDAR_DATE.exec(value);
  if (match === null) return false;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const utc = new Date(Date.UTC(year, month - 1, day));
  return (
    utc.getUTCFullYear() === year && utc.getUTCMonth() === month - 1 && utc.getUTCDate() === day
  );
}

/** The choice a URL parameter states; anything unreadable is the default. */
export function parseAsOf(value: string | null): AsOf {
  if (value === AUTO) return { kind: 'auto' };
  if (value !== null && isCalendarDate(value)) return { kind: 'date', date: value };
  return DEFAULT_AS_OF;
}

/** The URL parameter for a choice. */
export function formatAsOf(asOf: AsOf): string {
  return asOf.kind === 'auto' ? AUTO : asOf.date;
}

/** The `as_of` a run sends: the date, or null for Auto. */
export function requestAsOf(asOf: AsOf): string | null {
  return asOf.kind === 'auto' ? null : asOf.date;
}
