/**
 * Whether the window is too narrow for the office (spec §14 F6: below 768 px goes to Classic), followed
 * live. A browser without `matchMedia` counts as wide, as the office did before F6.
 */

import { useSyncExternalStore } from 'react';

/** The narrowest window, in CSS pixels, that gets the 3D office. */
export const OFFICE_MIN_WIDTH = 768;

const QUERY = `(min-width: ${OFFICE_MIN_WIDTH}px)`;

function media(): MediaQueryList | null {
  return typeof window.matchMedia === 'function' ? window.matchMedia(QUERY) : null;
}

function subscribe(onChange: () => void): () => void {
  const list = media();
  list?.addEventListener('change', onChange);
  return () => list?.removeEventListener('change', onChange);
}

export function useNarrowWindow(): boolean {
  return useSyncExternalStore(subscribe, () => {
    const list = media();
    return list !== null && !list.matches;
  });
}
