/**
 * What the office page hands the 3D world (spec §9). The world is a lazy chunk (§9.10), so the
 * page imports only these types from it: every value the world draws is computed here, from API
 * responses, before it crosses (D-F-1, AC-F-1).
 */

import type { AgentState, Bubble } from '@/domain/agentLook';
import type { Board } from '@/domain/monitor';
import type { Agent } from '@/domain/roster';

export interface WorldAgent {
  agent: Agent;
  state: AgentState;
  bubble: Bubble;
  detail: string;
}

/** SIGNALS_AGENT's board: the selected customer's signals, or why there are none. */
export type BoardState =
  { kind: 'loading' } | { kind: 'empty' } | { kind: 'error' } | { kind: 'ready'; board: Board };

/** One decision on the selected brief, as the CEO's corkboard pins it (§8.6). */
export interface CorkNote {
  ordinal: number;
  decision: 'APPROVED' | 'REJECTED';
}

export interface WorldProps {
  agents: readonly WorldAgent[];
  board: BoardState;
  /** The inbox's rows, for the paper in the CEO's tray; null until the inbox has loaded. */
  trayCount: number | null;
  notes: readonly CorkNote[];
  /** The agent whose panel is open. */
  openAgentId: string | null;
  highlightedAgentId: string | null;
  pixel: boolean;
  /** `?still=1`: nothing moves on its own, and the world renders on demand (§8.1). */
  still: boolean;
  /** `?perf=1`: the frame-time overlay (§9.10). */
  perf: boolean;
  reducedMotion: boolean;
  onOpenAgent: (agentId: string) => void;
  onOpenInbox: () => void;
  /** The first frame has been drawn. */
  onReady: () => void;
  onContextLost: () => void;
}
