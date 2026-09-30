/**
 * The office's sound (spec §9.12, D-F-19), only when the reader turned it on: soft keyboard clicks
 * while any agent WORKS, and a stamp's thump for each decision recorded while the office is open.
 */

import { useEffect, useRef } from 'react';

import { keyClick, stampThump } from '@/lib/sound';

import type { StampCue, WorldAgent } from './worldTypes';

/** How often a working office may click, in milliseconds. */
export const CLICK_EVERY_MS = 110;

export function useOfficeSound(
  agents: readonly WorldAgent[],
  stamp: StampCue | null,
  enabled: boolean,
): void {
  const working = enabled && agents.some((world) => world.state === 'WORKING');
  useEffect(() => {
    if (!working) return undefined;
    const timer = window.setInterval(() => {
      if (Math.random() < 0.7) keyClick();
    }, CLICK_EVERY_MS);
    return () => window.clearInterval(timer);
  }, [working]);

  // A stamp from before the office opened is not heard again.
  const heard = useRef(stamp?.id ?? 0);
  useEffect(() => {
    if (stamp === null || stamp.id === heard.current) return;
    heard.current = stamp.id;
    if (enabled) stampThump();
  }, [stamp, enabled]);
}
