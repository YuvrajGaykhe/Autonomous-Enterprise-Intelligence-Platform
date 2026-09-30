/**
 * Ambient life (spec §9.7; the owner's F4 ruling): an agent that is not at work takes a place in
 * the Break Area, stays a while, then moves to another free place there.
 *
 * It is deterministic: each agent draws from a generator seeded by a hash of its id, and places are
 * handed out in the order agents ask. `still` (no dwell) keeps every agent at its first place, so
 * screenshots are stable. Ambient life never touches an agent's state, bulb, glow or caption.
 */

import { BREAK_SPOTS, suits, type Spot } from './breakArea';
import type { AgentKind } from './roster';
import { hashString, seededRandom } from './seed';

/** How long an agent stays at a place, in seconds (PROPOSED): from the first to the second. */
export type Dwell = readonly [number, number];

export const AMBIENT_DWELL: Dwell = [7, 16];

interface Stay {
  spot: Spot;
  /** When the agent leaves for another place; Infinity until it has arrived, or when still. */
  until: number;
}

export class AmbientPlanner {
  private readonly stays = new Map<string, Stay>();
  private readonly occupied = new Map<string, string>();
  private readonly randoms = new Map<string, () => number>();
  private readonly dwell: Dwell | null;
  private readonly spots: readonly Spot[];

  /** `dwell` null: agents never move on (`still`). */
  constructor(dwell: Dwell | null, spots: readonly Spot[] = BREAK_SPOTS) {
    this.dwell = dwell;
    this.spots = spots;
  }

  private random(agentId: string): () => number {
    let random = this.randoms.get(agentId);
    if (random === undefined) {
      random = seededRandom(hashString(`break:${agentId}`));
      this.randoms.set(agentId, random);
    }
    return random;
  }

  private choose(agentId: string, kind: AgentKind, avoid: string | null): Spot | null {
    const free = this.spots.filter(
      (spot) => suits(kind, spot) && !this.occupied.has(spot.id) && spot.id !== avoid,
    );
    if (free.length === 0) return null;
    return free[Math.floor(this.random(agentId)() * free.length)] as Spot;
  }

  private take(agentId: string, spot: Spot): Spot {
    const previous = this.stays.get(agentId);
    if (previous !== undefined) this.occupied.delete(previous.spot.id);
    this.occupied.set(spot.id, agentId);
    this.stays.set(agentId, { spot, until: Infinity });
    return spot;
  }

  /**
   * The place an idle agent heads for, or keeps, at `now` (seconds). Null when the Break Area has
   * no free place for it.
   */
  spotFor(agentId: string, kind: AgentKind, now: number): Spot | null {
    const stay = this.stays.get(agentId);
    if (stay !== undefined && now < stay.until) return stay.spot;
    const next = this.choose(agentId, kind, stay?.spot.id ?? null);
    if (next === null) return stay?.spot ?? null;
    return this.take(agentId, next);
  }

  /** The agent reached its place at `now`: it stays for its dwell, then moves on. */
  arrived(agentId: string, now: number): void {
    const stay = this.stays.get(agentId);
    if (stay === undefined || stay.until !== Infinity || this.dwell === null) return;
    const [least, most] = this.dwell;
    stay.until = now + least + this.random(agentId)() * (most - least);
  }

  /** The agent went to work: its place is free for others. */
  release(agentId: string): void {
    const stay = this.stays.get(agentId);
    if (stay === undefined) return;
    this.occupied.delete(stay.spot.id);
    this.stays.delete(agentId);
  }

  /** Who holds which place, for tests and the text twin. */
  holders(): ReadonlyMap<string, string> {
    return this.occupied;
  }
}
