/**
 * The show the office plays (spec §9.4–§9.6, D-F-1, AC-F-2), and the latest decision's stamp.
 *
 * - `live`: a POST is in flight; its stages' agents work at their desks.
 * - `hold`: the POST has answered; they wait at their desks while the replay's data is read.
 * - `replay`: the recorded results, step by step, under the replay banner (Appendix A).
 *
 * At most one show plays at a time, and a new one replaces the old. The store keeps the show's
 * current frame, recomputed exactly when the timeline says it changes, and ends a replay when its
 * timeline does. Outside a show there is no frame, and every agent is idle in the Break Area.
 * Nothing here is persisted.
 */

import { create } from 'zustand';

import { frameAt, nextChange, type Frame, type Timeline } from '@/domain/director';

export type ShowKind = 'live' | 'hold' | 'replay';

export interface Show {
  id: number;
  kind: ShowKind;
  subject: 'assessment' | 'ingestion';
  timeline: Timeline;
  /** When it began, on the director's clock (milliseconds). */
  startedAt: number;
  /** A replay's banner; null for live and hold. */
  banner: string | null;
}

export interface StampState {
  id: number;
  decision: 'APPROVED' | 'REJECTED';
}

export interface DirectorState {
  show: Show | null;
  frame: Frame | null;
  stamp: StampState | null;
  /** Start a show now, replacing any other; returns its id. */
  begin: (show: Omit<Show, 'id' | 'startedAt'>) => number;
  /** End the show with this id, or whichever plays. */
  end: (id?: number) => void;
  /** Recompute the frame now, for a clock that jumped (a tab back from the background). */
  refresh: () => void;
  /** A decision was recorded (201): stamp it on the CEO's desk. */
  stampDecision: (decision: StampState['decision']) => void;
}

/** The director's clock, in milliseconds; tests may replace it. */
export const directorClock = { now: (): number => performance.now() };

let timer: ReturnType<typeof setTimeout> | null = null;
let shows = 0;

export const useDirector = create<DirectorState>()((set, get) => {
  /** Recompute the frame, and wake again when it next changes. */
  const tick = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    const show = get().show;
    if (show === null) return;
    const t = (directorClock.now() - show.startedAt) / 1000;
    const frame = frameAt(show.timeline, t);
    if (frame.ended) {
      set({ show: null, frame: null });
      return;
    }
    set({ frame });
    const next = nextChange(show.timeline, t);
    if (next !== Infinity) timer = setTimeout(tick, Math.max(0, (next - t) * 1000) + 4);
  };

  return {
    show: null,
    frame: null,
    stamp: null,
    begin: (show) => {
      shows += 1;
      // The old show's frame goes with it, so no agent follows a cue of the show before.
      set({ show: { ...show, id: shows, startedAt: directorClock.now() }, frame: null });
      tick();
      return shows;
    },
    end: (id) => {
      const show = get().show;
      if (show === null || (id !== undefined && show.id !== id)) return;
      if (timer !== null) clearTimeout(timer);
      timer = null;
      set({ show: null, frame: null });
    },
    refresh: tick,
    stampDecision: (decision) =>
      set((state) => ({ stamp: { id: (state.stamp?.id ?? 0) + 1, decision } })),
  };
});
