/**
 * Timestamps (spec §7.8).
 *
 * Calendar dates (`as_of`, `created_date`) are shown as the strings they are and never reach this
 * module. A timestamp such as `decided_at` is shown in local time, with its UTC form for a tooltip.
 */

export interface TimestampView {
  /** In the viewer's time zone, or the one given. */
  local: string;
  /** `2026-09-28 01:55:24 UTC`. */
  utc: string;
}

export function formatTimestamp(
  iso: string,
  options: { locale?: string; timeZone?: string } = {},
): TimestampView {
  const instant = new Date(iso);
  if (Number.isNaN(instant.getTime())) throw new Error(`not a timestamp: ${JSON.stringify(iso)}`);
  const local = new Intl.DateTimeFormat(options.locale, {
    dateStyle: 'medium',
    timeStyle: 'medium',
    ...(options.timeZone === undefined ? {} : { timeZone: options.timeZone }),
  }).format(instant);
  const utc = `${instant.toISOString().slice(0, 19).replace('T', ' ')} UTC`;
  return { local, utc };
}

/** A request's duration for "Show the API call", in whole milliseconds. */
export function formatDuration(milliseconds: number): string {
  return `${Math.round(milliseconds)} ms`;
}
