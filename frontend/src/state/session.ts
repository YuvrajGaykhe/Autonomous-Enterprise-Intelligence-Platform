/**
 * What this browser session remembers between pages (spec §7.2, §7.6, §8.4, §9.2, §9.11).
 * Nothing here is persisted: a reload starts clean.
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
  /** Set once the 3D office could not start, or lost its WebGL context twice (§9.11). */
  webglFailed: boolean;
  /** How many times the office's WebGL context was lost in this session. */
  contextLosses: number;
  /** The agent whose desk the office highlights after an evidence link opened (§8.4). */
  highlightedAgentId: string | null;
  setLastRun: (run: LastRun) => void;
  selectBrief: (briefId: string) => void;
  refuseBrief: (briefId: string, requestId: string | null) => void;
  failWebgl: () => void;
  /** Count a lost context; the second one in a session fails the office. */
  loseContext: () => void;
  highlight: (agentId: string | null) => void;
}

/** A lost context is survivable once; the second loss in a session falls back (§9.11). */
export const CONTEXT_LOSSES_TOLERATED = 1;

export const initialSession = {
  lastRun: null,
  selectedBriefId: null,
  refusedBriefs: {},
  webglFailed: false,
  contextLosses: 0,
  highlightedAgentId: null,
} satisfies Partial<SessionState>;

export const useSession = create<SessionState>()((set) => ({
  ...initialSession,
  setLastRun: (run) => set({ lastRun: run }),
  selectBrief: (briefId) => set({ selectedBriefId: briefId }),
  refuseBrief: (briefId, requestId) =>
    set((state) => ({ refusedBriefs: { ...state.refusedBriefs, [briefId]: requestId } })),
  failWebgl: () => set({ webglFailed: true }),
  loseContext: () =>
    set((state) => {
      const contextLosses = state.contextLosses + 1;
      return { contextLosses, webglFailed: contextLosses > CONTEXT_LOSSES_TOLERATED };
    }),
  highlight: (agentId) => set({ highlightedAgentId: agentId }),
}));
