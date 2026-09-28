import { useCallback } from 'react';
import { useSearchParams } from 'react-router';

import { formatAsOf, parseAsOf, type AsOf } from '@/domain/asOf';

export const AS_OF_PARAM = 'as_of';

/** The HUD's `as_of`, kept in the URL so every page and deep link shares it (§8.1). */
export function useAsOf(): [AsOf, (next: AsOf) => void] {
  const [params, setParams] = useSearchParams();
  const asOf = parseAsOf(params.get(AS_OF_PARAM));
  const setAsOf = useCallback(
    (next: AsOf) =>
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          updated.set(AS_OF_PARAM, formatAsOf(next));
          return updated;
        },
        { replace: true },
      ),
    [setParams],
  );
  return [asOf, setAsOf];
}
