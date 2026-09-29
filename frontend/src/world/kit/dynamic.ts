/**
 * The parts that follow the data (spec §9.3, §9.5, §8.6): each agent's antenna bulb in its state's
 * colour, the paper in the CEO's tray (one sheet per inbox row) and the corkboard's notes (one per
 * decision on the selected brief, stamped APPROVED or REJECTED).
 */

import { LOOKS, type BulbColour } from '@/domain/agentLook';
import { FURNITURE } from '@/domain/floorPlan';
import type { CorkNote, WorldAgent } from '@/office/worldTypes';

import type { Body } from './characters';
import { box, part, placed, type Part } from './parts';

export const BULB_HEX: Readonly<Record<BulbColour, string>> = {
  idle: '#a1a1aa',
  working: '#22d3ee',
  waiting: '#fbbf24',
  done: '#22c55e',
  error: '#ef4444',
};

export const GLOW_HEX = '#39ff88';

/** The most sheets the tray shows; more rows keep the same stack. */
export const TRAY_SHEETS = 8;
/** The most notes the corkboard holds. */
export const CORK_NOTES = 6;

const STAMP: Readonly<Record<CorkNote['decision'], string>> = {
  APPROVED: '#2e9e5b',
  REJECTED: '#c0392b',
};

export function bulbParts(
  agents: readonly WorldAgent[],
  bodies: ReadonlyMap<string, Body | null>,
): Part[] {
  return agents.flatMap((world) => {
    const body = bodies.get(world.agent.id);
    if (body === undefined || body === null) return [];
    return [
      part(
        'sphere',
        BULB_HEX[LOOKS[world.state].bulb],
        [0.14, 0.14, 0.14],
        body.bulb,
        [0, 0, 0],
        'glow',
      ),
    ];
  });
}

export function trayParts(count: number | null): Part[] {
  const desk = FURNITURE.find((item) => item.kind === 'executiveDesk');
  if (desk === undefined || count === null) return [];
  const sheets = Array.from({ length: Math.min(count, TRAY_SHEETS) }, (_, index) =>
    box(
      index % 2 === 0 ? '#fbfaf5' : '#efece2',
      [0.38, 0.014, 0.27],
      [0.62, 0.86 + index * 0.016, 0.05],
      [0, (index % 3) * 0.05 - 0.05, 0],
    ),
  );
  return placed(sheets, desk.x, 0, desk.z, desk.rotation);
}

export function noteParts(notes: readonly CorkNote[]): Part[] {
  const board = FURNITURE.find((item) => item.kind === 'corkboard');
  if (board === undefined) return [];
  const local = notes.slice(0, CORK_NOTES).flatMap((note, index) => {
    const x = -0.44 + (index % 3) * 0.44;
    const y = 1.58 - Math.floor(index / 3) * 0.42;
    return [
      box('#fdf6d8', [0.34, 0.3, 0.012], [x, y, 0.05]),
      box(STAMP[note.decision], [0.26, 0.07, 0.014], [x, y - 0.04, 0.058], [0, 0, -0.12]),
      part('sphere', '#c0392b', [0.05, 0.05, 0.05], [x, y + 0.12, 0.065]),
    ];
  });
  return placed(local, board.x, 0, board.z, board.rotation);
}
