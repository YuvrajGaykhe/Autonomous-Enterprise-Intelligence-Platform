/**
 * The building (spec §9.1, §9.3): floors, walls, windows and the locked rooms' barriers. A warm
 * wood floor, cream walls; the far outer walls stand tall with windows, every other wall is a low
 * partition so the floor stays in view (§9.8).
 */

import {
  FLOOR,
  ROOM_RECTS,
  WALL_HEIGHT,
  WALL_LINES,
  WALL_THICKNESS,
  isFarWall,
  wallSegments,
  type Rect,
  type WallLine,
} from '@/domain/floorPlan';
import { ROOMS, isLocked, type RoomId } from '@/domain/roster';
import { hashString } from '@/domain/seed';

import { box, glowBox, part, type Part } from './parts';

export const PALETTE = {
  wall: '#f3e6c9',
  wallTrim: '#cdb48a',
  window: '#bfe0f7',
  windowFrame: '#8a6a45',
  lockedTile: ['#6f757e', '#656a73'],
  barrier: ['#f2c230', '#2a2a2e'],
} as const;

/** Each open room's plank colours (PROPOSED): warm wood, a concrete dock, a darker CEO floor. */
const FLOORS: Readonly<Record<RoomId, readonly [string, string, string]>> = {
  'data-dock': ['#9aa1a8', '#939aa2', '#a1a7ae'],
  'evidence-lab': ['#d5a56c', '#cf9d63', '#dbad75'],
  'signals-desk': ['#c8894f', '#c08148', '#cf9157'],
  'ceo-office': ['#8e5a35', '#86532f', '#95613b'],
  'analyst-bullpen': ['#c8894f', '#c08148', '#cf9157'],
  'debate-table': ['#d5a56c', '#cf9d63', '#dbad75'],
  'brief-studio': ['#c8894f', '#c08148', '#cf9157'],
  'break-area': ['#b98a5a', '#b28353', '#c09262'],
  'pipeline-room': ['#6f757e', '#656a73', '#6f757e'],
  'account-360': ['#6f757e', '#656a73', '#6f757e'],
  'war-room': ['#6f757e', '#656a73', '#6f757e'],
  'copilot-desk': ['#6f757e', '#656a73', '#6f757e'],
};

const PLANK = 0.5;
const SLAB = 0.1;

function planks(id: RoomId, rect: Rect): Part[] {
  const colours = FLOORS[id];
  const parts: Part[] = [];
  for (let index = 0; index * PLANK < rect.depth; index += 1) {
    const colour = colours[hashString(`${id}:${index}`) % colours.length] as string;
    parts.push(
      box(
        colour,
        [rect.width, SLAB, PLANK],
        [rect.x + rect.width / 2, -SLAB / 2, rect.z + index * PLANK + PLANK / 2],
      ),
    );
  }
  return parts;
}

function tiles(rect: Rect): Part[] {
  const parts: Part[] = [];
  for (let x = 0; x < rect.width; x += 1)
    for (let z = 0; z < rect.depth; z += 1)
      parts.push(
        box(
          PALETTE.lockedTile[(x + z) % 2] as string,
          [1, SLAB, 1],
          [rect.x + x + 0.5, -SLAB / 2, rect.z + z + 0.5],
        ),
      );
  return parts;
}

export function floorParts(): Part[] {
  return ROOMS.flatMap((room) =>
    isLocked(room) ? tiles(ROOM_RECTS[room.id]) : planks(room.id, ROOM_RECTS[room.id]),
  );
}

function wallHeight(line: WallLine, yaw: number): number {
  return line.side !== undefined && isFarWall(line.side, yaw) ? WALL_HEIGHT.tall : WALL_HEIGHT.low;
}

/** A stretch of wall from `from` to `to` along the line, with its trim. */
function stretch(line: WallLine, from: number, to: number, height: number): Part[] {
  const length = to - from;
  const middle = (from + to) / 2;
  const along = line.axis === 'x';
  const size = (width: number, tall: number, deep: number) =>
    along ? ([width, tall, deep] as const) : ([deep, tall, width] as const);
  const at = (y: number) =>
    along ? ([middle, y, line.at] as const) : ([line.at, y, middle] as const);
  return [
    box(PALETTE.wall, size(length, height, WALL_THICKNESS), at(height / 2)),
    box(PALETTE.wallTrim, size(length, 0.06, WALL_THICKNESS + 0.04), at(height + 0.03)),
  ];
}

/** Where interior walls meet each outer wall: windows stay between them. */
const JUNCTIONS: Readonly<Record<string, readonly number[]>> = {
  north: [10, 17, 24],
  south: [8, 16, 24],
  west: [8, 15],
  east: [8, 15],
};

function windows(line: WallLine): Part[] {
  const stops = [line.from, ...(JUNCTIONS[line.side ?? ''] ?? []), line.to];
  const parts: Part[] = [];
  const inward = line.side === 'north' || line.side === 'west' ? 1 : -1;
  for (let index = 0; index + 1 < stops.length; index += 1) {
    const [start, end] = [stops[index] as number, stops[index + 1] as number];
    const count = Math.max(1, Math.floor((end - start) / 3));
    for (let pane = 0; pane < count; pane += 1) {
      const centre = start + ((pane + 0.5) * (end - start)) / count;
      const offset = inward * (WALL_THICKNESS / 2 + 0.01);
      const at = (y: number, depth = 0) =>
        line.axis === 'x'
          ? ([centre, y, line.at + offset + depth] as const)
          : ([line.at + offset + depth, y, centre] as const);
      const size = (width: number, height: number, deep: number) =>
        line.axis === 'x' ? ([width, height, deep] as const) : ([deep, height, width] as const);
      parts.push(
        box(PALETTE.windowFrame, size(1.5, 1.05, 0.04), at(1.5)),
        glowBox(PALETTE.window, size(1.3, 0.85, 0.04), at(1.5, inward * 0.01)),
        box(PALETTE.windowFrame, size(0.05, 0.85, 0.05), at(1.5, inward * 0.02)),
      );
    }
  }
  return parts;
}

/** A closed door in a locked room's wall: striped barrier posts and a padlock (D-F-4). */
function barrier(line: WallLine, door: number): Part[] {
  const at = (along: number, y: number): readonly [number, number, number] =>
    line.axis === 'x' ? [along, y, line.at] : [line.at, y, along];
  const parts: Part[] = [];
  for (const side of [-0.8, 0.8]) {
    parts.push(part('cylinder', PALETTE.barrier[0], [0.14, 1.2, 0.14], at(door + side, 0.6)));
  }
  for (let stripe = 0; stripe < 8; stripe += 1) {
    const along = door - 0.7 + stripe * 0.2;
    parts.push(
      box(
        PALETTE.barrier[stripe % 2] as string,
        line.axis === 'x' ? [0.2, 0.12, 0.08] : [0.08, 0.12, 0.2],
        at(along, 1.1),
      ),
    );
  }
  parts.push(
    box('#d9a520', [0.22, 0.2, 0.12], at(door, WALL_HEIGHT.low + 0.14)),
    part('torus', '#9aa0a6', [0.18, 0.18, 0.18], at(door, WALL_HEIGHT.low + 0.3)),
  );
  return parts;
}

/** Every wall at camera yaw `yaw`, with windows in the tall ones. */
export function wallParts(yaw: number): Part[] {
  return WALL_LINES.flatMap((line) => {
    const height = wallHeight(line, yaw);
    return [
      ...wallSegments(line).flatMap(([from, to]) => stretch(line, from, to, height)),
      ...(height === WALL_HEIGHT.tall ? windows(line) : []),
      ...(line.kind === 'locked' ? line.doors.flatMap((door) => barrier(line, door)) : []),
    ];
  });
}

/** The ground outside the building, so the office sits on something. */
export function groundParts(): Part[] {
  return [
    box(
      '#3a332d',
      [FLOOR.width + 6, 0.05, FLOOR.depth + 6],
      [FLOOR.width / 2, -0.13, FLOOR.depth / 2],
    ),
  ];
}
