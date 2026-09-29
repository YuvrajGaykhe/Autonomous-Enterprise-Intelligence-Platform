/**
 * The world's parts (spec §9.3, §9.8, §9.9): the building, the furniture, the bodies and the parts
 * that follow the data. They are plain lists of parts, so they are checked without WebGL.
 */

import { Vector3 } from 'three';
import { describe, expect, it } from 'vitest';

import { LOOKS } from '@/domain/agentLook';
import { FURNITURE, WALL_HEIGHT, seatsFor, type FurnitureKind } from '@/domain/floorPlan';
import { rosterFor } from '@/domain/roster';
import type { WorldAgent } from '@/office/worldTypes';
import { floorParts, groundParts, wallParts } from '@/world/kit/building';
import { bodyFor, bulbHeight } from '@/world/kit/characters';
import {
  BULB_HEX,
  CORK_NOTES,
  TRAY_SHEETS,
  bulbParts,
  noteParts,
  trayParts,
} from '@/world/kit/dynamic';
import { furnitureParts } from '@/world/kit/furniture';
import { outlined, part, placed, type Part } from '@/world/kit/parts';

const roster = rosterFor([{ source: 'csv_demo' }, { source: 'odoo_mock' }]);
const seats = seatsFor(roster);

function centre(item: Part): Vector3 {
  return new Vector3().setFromMatrixPosition(item.matrix);
}

describe('parts', () => {
  it('places parts in a frame, and hulls them for the glow', () => {
    const local = [part('box', '#fff', [1, 1, 1], [1, 0, 0])];
    const [moved] = placed(local, 10, 0, 5, Math.PI / 2);
    expect(
      centre(moved as Part)
        .toArray()
        .map((value) => Math.round(value * 1e6) / 1e6),
    ).toEqual([10, 0, 4]);
    const [hull] = outlined(local, '#39ff88');
    expect(hull).toMatchObject({ finish: 'outline', color: '#39ff88', shape: 'box' });
    expect(new Vector3().setFromMatrixScale((hull as Part).matrix).x).toBeCloseTo(1.14);
  });
});

describe('the building (§9.1, §9.8)', () => {
  it('floors every room, and the ground under it', () => {
    expect(floorParts().length).toBeGreaterThan(100);
    expect(groundParts()).toHaveLength(1);
  });

  it('stands the far walls tall, with windows, at the starting yaw', () => {
    const walls = wallParts(45);
    const heights = walls
      .filter((item) => item.color === '#f3e6c9')
      .map((item) => new Vector3().setFromMatrixScale(item.matrix).y);
    expect(Math.max(...heights)).toBe(WALL_HEIGHT.tall);
    expect(Math.min(...heights)).toBe(WALL_HEIGHT.low);
    expect(walls.some((item) => item.finish === 'glow')).toBe(true);
  });

  it('turns which walls stand tall with the camera', () => {
    const tallAt = (yaw: number) =>
      wallParts(yaw)
        .filter((item) => new Vector3().setFromMatrixScale(item.matrix).y === WALL_HEIGHT.tall)
        .map((item) => centre(item).toArray().join(','));
    expect(tallAt(45)).not.toEqual(tallAt(225));
  });
});

describe('the furniture (§9.8)', () => {
  it('builds every kind the floor plan uses, the board apart', () => {
    for (const item of FURNITURE) {
      const parts = furnitureParts(item);
      if (item.kind === 'signalsBoard') expect(parts).toEqual([]);
      else expect(parts.length).toBeGreaterThan(0);
    }
    const kinds = new Set<FurnitureKind>(FURNITURE.map((item) => item.kind));
    expect(kinds.size).toBeGreaterThan(20);
  });
});

describe('the bodies (§9.9)', () => {
  it('gives every agent but the CEO a body, with its bulb above its head', () => {
    for (const agent of roster) {
      const seat = seats.get(agent.id);
      if (seat === undefined) throw new Error(`no seat for ${agent.id}`);
      const body = bodyFor(agent.id, agent.kind, seat);
      if (agent.kind === 'ceo') {
        expect(body).toBeNull();
        continue;
      }
      expect(body?.parts.length).toBeGreaterThan(10);
      expect(body?.bulb).toEqual([seat.x, bulbHeight(agent.kind, seat.pose), seat.z]);
    }
  });

  it('keeps the same looks for the same agent', () => {
    const seat = seats.get('linker');
    if (seat === undefined) throw new Error('no seat for linker');
    const colours = (id: string) => bodyFor(id, 'linker', seat)?.parts.map((item) => item.color);
    expect(colours('linker')).toEqual(colours('linker'));
  });

  it('puts the robot’s bulb higher than a person’s', () => {
    expect(bulbHeight('memory', 'stand')).toBeGreaterThan(bulbHeight('linker', 'stand'));
    expect(bulbHeight('linker', 'sit')).toBeGreaterThan(bulbHeight('linker', 'stand'));
  });
});

describe('the parts that follow the data (§9.3, §9.5, §8.6)', () => {
  const agents: WorldAgent[] = roster.map((agent, index) => ({
    agent,
    state: index === 1 ? 'ERROR' : 'IDLE',
    bubble: null,
    detail: '',
  }));
  const bodies = new Map(
    roster.map((agent) => {
      const seat = seats.get(agent.id);
      return [agent.id, seat === undefined ? null : bodyFor(agent.id, agent.kind, seat)];
    }),
  );

  it("lights each agent's bulb in its state's colour, and none for the CEO", () => {
    const bulbs = bulbParts(agents, bodies);
    expect(bulbs).toHaveLength(roster.length - 1);
    expect(bulbs[1]?.color).toBe(BULB_HEX[LOOKS.ERROR.bulb]);
    expect(bulbs.every((item) => item.finish === 'glow')).toBe(true);
    expect(bulbParts(agents, new Map())).toEqual([]);
  });

  it('stacks one sheet per inbox row in the tray, up to the tray’s height', () => {
    expect(trayParts(null)).toEqual([]);
    expect(trayParts(3)).toHaveLength(3);
    expect(trayParts(50)).toHaveLength(TRAY_SHEETS);
  });

  it('pins one note per decision, stamped by the decision', () => {
    expect(noteParts([])).toEqual([]);
    const notes = noteParts([
      { ordinal: 1, decision: 'APPROVED' },
      { ordinal: 2, decision: 'REJECTED' },
    ]);
    expect(notes.map((item) => item.color)).toEqual([
      '#fdf6d8',
      '#2e9e5b',
      '#c0392b',
      '#fdf6d8',
      '#c0392b',
      '#c0392b',
    ]);
    const many = Array.from({ length: 9 }, (_, index) => ({
      ordinal: index + 1,
      decision: 'APPROVED' as const,
    }));
    expect(noteParts(many)).toHaveLength(CORK_NOTES * 3);
  });
});
