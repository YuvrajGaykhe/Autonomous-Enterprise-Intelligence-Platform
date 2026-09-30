/**
 * The office as the Director and the walkers see it (spec §9.5–§9.7): every agent's place, the
 * walk grid of this roster's furniture, and how long walks take. One layout per roster.
 */

import type { Layout } from './director';
import { officeFurniture, seatsFor } from './floorPlan';
import type { Agent } from './roster';
import { buildWalkGrid, walkSeconds, type Point, type WalkGrid } from './walkGrid';

export interface OfficeLayout extends Layout {
  grid: WalkGrid;
}

/** The middle of the Break Area, where the gather's walk is measured from. */
export const BREAK_MIDDLE: Point = [27, 12.4];
/** Slack on a gather, for an agent sitting at the far end of the Break Area. */
export const GATHER_SLACK = 1;

const cache = new Map<string, OfficeLayout>();

export function officeLayout(roster: readonly Agent[]): OfficeLayout {
  const key = roster.map((agent) => agent.id).join(' ');
  let layout = cache.get(key);
  if (layout === undefined) {
    const grid = buildWalkGrid(officeFurniture(roster));
    layout = {
      roster,
      seats: seatsFor(roster),
      grid,
      walkSeconds: (from, to) => walkSeconds(grid, from, to),
    };
    cache.set(key, layout);
  }
  return layout;
}

/** How long `cast` needs to walk from the Break Area to their desks. */
export function gatherSeconds(layout: Layout, cast: readonly string[]): number {
  const walks = cast.map((agentId) => {
    const seat = layout.seats.get(agentId);
    return seat === undefined ? 0 : layout.walkSeconds(BREAK_MIDDLE, [seat.x, seat.z]);
  });
  return Math.max(0, ...walks) + GATHER_SLACK;
}
