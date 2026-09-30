/**
 * The world's parts (spec §9.3, §9.8, §9.9): the building, the furniture, the bodies, how they
 * move (F4), the arrows' arcs and the parts that follow the data. They are plain lists of parts
 * and numbers, so they are checked without WebGL.
 */

import { Vector3 } from 'three';
import { describe, expect, it } from 'vitest';

import { LOOKS } from '@/domain/agentLook';
import { FURNITURE, WALL_HEIGHT, seatsFor, type FurnitureKind } from '@/domain/floorPlan';
import { rosterFor } from '@/domain/roster';
import { arcPoint, arrowLabelAnchor, END_HEIGHT } from '@/world/kit/arrows';
import { floorParts, groundParts, wallParts } from '@/world/kit/building';
import { bodyFor, bulbHeight, rigFor } from '@/world/kit/characters';
import {
  BULB_HEX,
  CORK_NOTES,
  TRAY_SHEETS,
  noteParts,
  trayParts,
  trayTop,
} from '@/world/kit/dynamic';
import { limbs, segmentMatrices, type Animation } from '@/world/kit/motion';
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
  it('has a bulb colour for every look', () => {
    for (const look of Object.values(LOOKS)) expect(BULB_HEX[look.bulb]).toMatch(/^#[0-9a-f]{6}$/);
  });

  it('lands the stamp on the top sheet of the tray', () => {
    expect(trayTop(null)).toBeCloseTo(0.872);
    expect(trayTop(3)).toBeGreaterThan(trayTop(1));
    expect(trayTop(50)).toBe(trayTop(TRAY_SHEETS));
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

describe('how bodies move (§9.9, §9.11; F4)', () => {
  const at = (matrix: { elements: ArrayLike<number> }, y: number, z: number) =>
    new Vector3(0, y, z).applyMatrix4(matrix as never);

  it('rigs every agent but the CEO in both poses, limbs apart from the body', () => {
    for (const agent of roster) {
      const stand = rigFor(agent.id, agent.kind, 'stand');
      const sit = rigFor(agent.id, agent.kind, 'sit');
      if (agent.kind === 'ceo') {
        expect(stand).toBeNull();
        continue;
      }
      const segments = new Set(stand?.parts.map((item) => item.segment));
      expect([...segments].sort()).toEqual(['armLeft', 'armRight', 'body', 'legLeft', 'legRight']);
      expect(stand?.bulb).toBe(bulbHeight(agent.kind, 'stand'));
      // MEMORY is a robot: it never sits.
      expect(sit?.pose).toBe(agent.kind === 'memory' ? 'stand' : 'sit');
    }
  });

  it('swings the legs and arms in opposition while walking, and not without animation', () => {
    const walk = limbs('walk', Math.PI / 2, 0, true);
    expect(walk.legLeft).toBeCloseTo(0.55);
    expect(walk.legRight).toBeCloseTo(-0.55);
    expect(walk.armLeft).toBeCloseTo(-0.45);
    const still = limbs('walk', Math.PI / 2, 0, false);
    for (const angle of Object.values(still)) expect(angle).toBeCloseTo(0);
  });

  it('has a shape for every pose, and keeps it without animation', () => {
    const animations: Animation[] = [
      'idle',
      'walk',
      'type',
      'work',
      'present',
      'play',
      'sip',
      'cheer',
      'carry',
      'carryWalk',
    ];
    for (const animation of animations)
      for (const time of [0, 1.3, 2.9, 3.1])
        expect(Number.isFinite(limbs(animation, time, time, true).armRight)).toBe(true);
    expect(limbs('cheer', 0, 0, false).armLeft).toBeCloseTo(-2.9);
    expect(limbs('carry', 0, 0, false)).toMatchObject({ armLeft: -1, armRight: -1 });
    expect(limbs('present', 0, 0, false).armRight).toBeCloseTo(-1.5);
    expect(limbs('sip', 0, 3, true).armRight).toBeLessThan(-0.5);
    expect(limbs('sip', 0, 1, true).armRight).toBe(-0.5);
  });

  it('turns a limb about its hip or shoulder, and keeps a seated body’s legs still', () => {
    const rig = rigFor('linker', 'linker', 'stand');
    const seated = rigFor('linker', 'linker', 'sit');
    if (rig === null || seated === null) throw new Error('no rig');
    const pose = { bob: 0, legLeft: 0.5, legRight: -0.5, armLeft: -1, armRight: 1 };
    const matrices = segmentMatrices(rig, pose);
    // The hip stays where it is; a positive angle swings the foot back, a negative one forward.
    expect(at(matrices.legLeft, rig.hip, 0).y).toBeCloseTo(rig.hip);
    expect(at(matrices.legLeft, 0, 0).z).toBeLessThan(-0.1);
    expect(at(matrices.legRight, 0, 0).z).toBeGreaterThan(0.1);
    expect(at(matrices.armLeft, rig.shoulder, 0).y).toBeCloseTo(rig.shoulder);
    expect(at(matrices.armLeft, rig.shoulder - 0.4, 0).z).toBeGreaterThan(0.2);
    const still = segmentMatrices(seated, pose);
    expect(at(still.legLeft, 0, 0).z).toBeCloseTo(0);
    expect(at(still.body, 1, 2).toArray()).toEqual([0, 1, 2]);
  });
});

describe('the neon arrows (§9.3, §9.5)', () => {
  const arrow = { id: 'a', from: [0, 0], to: [10, 0], tone: 'handoff', label: 'X' } as const;

  it('rises from end to end in an arc, higher for a longer one', () => {
    expect(arcPoint(arrow, 0)).toEqual([0, END_HEIGHT, 0]);
    expect(arcPoint(arrow, 1)).toEqual([10, END_HEIGHT, 0]);
    const top = arcPoint(arrow, 0.5)[1];
    expect(top).toBeGreaterThan(END_HEIGHT);
    expect(arcPoint({ ...arrow, to: [2, 0] }, 0.5)[1]).toBeLessThan(top);
    expect(arcPoint({ ...arrow, to: [200, 0] }, 0.5)[1]).toBeCloseTo(END_HEIGHT + 2.4);
  });

  it('floats its label just over its top', () => {
    const [x, y, z] = arrowLabelAnchor(arrow);
    expect([x, z]).toEqual([5, 0]);
    expect(y).toBeCloseTo(arcPoint(arrow, 0.5)[1] + 0.35);
  });
});
