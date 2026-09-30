/**
 * The tour's state (F6): whether it is open, and on which step. Closing it remembers, in this
 * browser, that the reader has seen it (`aiceohq.tour`, §11); without storage it simply opens again
 * on the next visit.
 */

import { create } from 'zustand';

import { moveStep, TOUR_SEEN, TOUR_STEPS, tourOpensOnArrival, type TourSpot } from '@/domain/tour';
import { STORAGE_KEYS, readStored, writeStored } from '@/lib/storage';

export interface TourState {
  open: boolean;
  step: number;
  /** Open at the first step, unless this browser has seen the tour (the app shell calls it). */
  arrive: () => void;
  /** Open at the first step (the HUD's "?"). */
  start: () => void;
  move: (delta: number) => void;
  close: () => void;
}

export const initialTour = { open: false, step: 0 } satisfies Partial<TourState>;

export const useTour = create<TourState>()((set) => ({
  ...initialTour,
  arrive: () => {
    if (tourOpensOnArrival(readStored(STORAGE_KEYS.tour))) set({ open: true, step: 0 });
  },
  start: () => set({ open: true, step: 0 }),
  move: (delta) => set((state) => ({ step: moveStep(state.step, delta) })),
  close: () => {
    writeStored(STORAGE_KEYS.tour, TOUR_SEEN);
    set({ open: false });
  },
}));

/** `data-tour-spot` for the part of the page that `spot` names: `on` while the tour points at it. */
export function useTourSpot(spot: TourSpot): 'on' | undefined {
  return useTour((state) =>
    state.open && TOUR_STEPS[state.step]?.spot === spot ? 'on' : undefined,
  );
}
