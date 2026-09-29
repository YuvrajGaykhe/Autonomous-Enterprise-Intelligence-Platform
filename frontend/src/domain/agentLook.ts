/**
 * How an agent looks in the office (spec §9.3, §9.4, §8.7; D-F-1).
 *
 * An agent's state picks its antenna bulb, its glyph and word, and whether it glows. Only WORKING
 * and HANDOFF glow, and only a real request in flight or a bannered replay enters them (F4). Until
 * then an agent is IDLE, WAITING (the CEO desk, with a PENDING brief in the shown snapshot) or in
 * ERROR (its request failed), and it shows a "…" bubble while its data loads.
 */

export type AgentState = 'IDLE' | 'WORKING' | 'HANDOFF' | 'WAITING' | 'DONE' | 'ERROR';

export type BulbColour = 'idle' | 'working' | 'waiting' | 'done' | 'error';

export interface Look {
  bulb: BulbColour;
  /** Shown with the colour, which never carries the meaning alone (§10). */
  glyph: string;
  glow: boolean;
}

export const LOOKS: Readonly<Record<AgentState, Look>> = {
  IDLE: { bulb: 'idle', glyph: '○', glow: false },
  WORKING: { bulb: 'working', glyph: '▶', glow: true },
  HANDOFF: { bulb: 'working', glyph: '➜', glow: true },
  WAITING: { bulb: 'waiting', glyph: '?', glow: false },
  DONE: { bulb: 'done', glyph: '✓', glow: false },
  ERROR: { bulb: 'error', glyph: '!', glow: false },
};

/** What the requests behind an agent say, once combined. */
export type Readiness =
  | { kind: 'loading' }
  | { kind: 'failed'; reason: string }
  | { kind: 'ready'; pendingBriefs?: number };

export type Bubble = 'loading' | 'waiting' | null;

export interface OfficeStatus {
  state: AgentState;
  bubble: Bubble;
  /** One line for the staff directory and the name tag's label. */
  detail: string;
}

/** The first failure, else loading while anything loads, else ready with the last pending count. */
export function combine(...parts: readonly Readiness[]): Readiness {
  const failed = parts.find((part) => part.kind === 'failed');
  if (failed !== undefined) return failed;
  if (parts.some((part) => part.kind === 'loading')) return { kind: 'loading' };
  const pending = parts.findLast(
    (part): part is Extract<Readiness, { kind: 'ready' }> =>
      part.kind === 'ready' && part.pendingBriefs !== undefined,
  );
  return pending ?? { kind: 'ready' };
}

function briefs(count: number): string {
  return count === 1 ? '1 brief awaits your decision' : `${count} briefs await your decision`;
}

/** The static office state of one agent (F3): no request here makes an agent WORKING. */
export function officeStatus(readiness: Readiness): OfficeStatus {
  switch (readiness.kind) {
    case 'loading':
      return { state: 'IDLE', bubble: 'loading', detail: 'Loading its data…' };
    case 'failed':
      return { state: 'ERROR', bubble: null, detail: readiness.reason };
    case 'ready': {
      const pending = readiness.pendingBriefs ?? 0;
      return pending > 0
        ? { state: 'WAITING', bubble: 'waiting', detail: briefs(pending) }
        : { state: 'IDLE', bubble: null, detail: 'Idle' };
    }
  }
}
