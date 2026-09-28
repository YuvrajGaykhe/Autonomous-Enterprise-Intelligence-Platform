/**
 * What this browser session remembers between pages (spec §7.2, §7.6, §9.2). Nothing here is
 * persisted: a reload starts clean.
 */

import { create } from 'zustand';

import type { AsOf } from '@/domain/asOf';

export interface LastRun {
  requested: AsOf;
  /** The date the run assessed at: the chosen date, or the one Auto resolved to. */
  asOf: string | null;
  status: number;
  assessmentIds: string[];
  briefCount: number;
  createdCount: number;
}

export interface SessionState {
  /** The latest assessment run in this session: the inbox shows its snapshot (§7.2). */
  lastRun: LastRun | null;
  /** The brief the agent pages show (§9.2); by default the inbox's first row. */
  selectedBriefId: string | null;
  /** Briefs whose stored payload no longer matches its hash, with the refusal's request id. */
  refusedBriefs: Readonly<Record<string, string | null>>;
  setLastRun: (run: LastRun) => void;
  selectBrief: (briefId: string) => void;
  refuseBrief: (briefId: string, requestId: string | null) => void;
}

export const initialSession = {
  lastRun: null,
  selectedBriefId: null,
  refusedBriefs: {},
} satisfies Partial<SessionState>;

export const useSession = create<SessionState>()((set) => ({
  ...initialSession,
  setLastRun: (run) => set({ lastRun: run }),
  selectBrief: (briefId) => set({ selectedBriefId: briefId }),
  refuseBrief: (briefId, requestId) =>
    set((state) => ({ refusedBriefs: { ...state.refusedBriefs, [briefId]: requestId } })),
}));
