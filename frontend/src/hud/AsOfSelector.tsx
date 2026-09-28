/**
 * The `as_of` selector (D-F-14): the explicit date 2026-09-18 by default, or Auto (latest ticket).
 */

import { useId } from 'react';

import { AUTO, DEFAULT_AS_OF_DATE, isCalendarDate } from '@/domain/asOf';

import { useAsOf } from './useAsOf';

export function AsOfSelector() {
  const [asOf, setAsOf] = useAsOf();
  const modeId = useId();
  const dateId = useId();
  return (
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor={modeId} className="font-mono text-xs text-muted-foreground">
        as_of
      </label>
      <select
        id={modeId}
        className="h-8 rounded-md border bg-card px-2"
        value={asOf.kind === 'auto' ? AUTO : 'date'}
        onChange={(event) =>
          setAsOf(
            event.target.value === AUTO
              ? { kind: 'auto' }
              : { kind: 'date', date: DEFAULT_AS_OF_DATE },
          )
        }
      >
        <option value="date">Date</option>
        <option value={AUTO}>Auto (latest ticket)</option>
      </select>
      {asOf.kind === 'date' && (
        <>
          <label htmlFor={dateId} className="sr-only">
            as_of date
          </label>
          <input
            id={dateId}
            type="date"
            className="h-8 rounded-md border bg-card px-2 font-mono"
            value={asOf.date}
            onChange={(event) => {
              if (isCalendarDate(event.target.value)) {
                setAsOf({ kind: 'date', date: event.target.value });
              }
            }}
          />
        </>
      )}
    </div>
  );
}
