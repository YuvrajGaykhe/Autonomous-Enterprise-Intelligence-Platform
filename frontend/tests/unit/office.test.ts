/**
 * The office's pure modules (spec §9): the floor plan, the camera, the agents' looks, the SIGNALS
 * board, the seeds and the performance record.
 */

import { describe, expect, it } from 'vitest';

import { LOOKS, combine, officeStatus, type AgentState } from '@/domain/agentLook';
import { signalRows } from '@/domain/briefView';
import {
  DOOR_WIDTH,
  FLOOR,
  FURNITURE,
  ROOM_LABEL_POINTS,
  ROOM_RECTS,
  WALL_LINES,
  connectorProps,
  connectorSeat,
  doorLinks,
  inRect,
  isFarWall,
  rectCenter,
  roomAt,
  seatsFor,
  wallSegments,
} from '@/domain/floorPlan';
import { BOARD_VALUE_WIDTH, boardColumns, clip, signalsBoard } from '@/domain/monitor';
import {
  CAMERA_DISTANCE,
  EDGE_STRENGTH,
  ZOOM_STOPS,
  cameraBasis,
  cameraPosition,
  cellCssPixels,
  clampTarget,
  clampZoom,
  fitPixelsPerUnit,
  panTarget,
  pixelSize,
  projectedExtent,
  snapTarget,
  yawDegrees,
  zoomScale,
  type Vec3,
} from '@/domain/officeCamera';
import { PERF_BUDGET, percentile, recent, summarize, type FrameSample } from '@/domain/perf';
import { FIXED_AGENTS, ROOMS, evidenceDesk, isLocked, rosterFor } from '@/domain/roster';
import { hashString, pick, seededRandom } from '@/domain/seed';
import type { AssessmentDetail } from '@/api/schemas/risk';

import { loadExchanges, recordedBody } from '../support/fixtures';

const sources = recordedBody<{ sources: { source: string }[] }>(
  'sources.json',
  'GET',
  '/api/v1/sources',
).sources;
const roster = rosterFor(sources);

const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

describe('the floor plan (§9.1)', () => {
  it('tiles the floor with every room, open rooms first, without overlap', () => {
    expect(Object.keys(ROOM_RECTS).sort()).toEqual(ROOMS.map((room) => room.id).sort());
    const area = Object.values(ROOM_RECTS).reduce((sum, rect) => sum + rect.width * rect.depth, 0);
    expect(area).toBe(FLOOR.width * FLOOR.depth);
    for (const room of ROOMS) {
      const [x, z] = rectCenter(ROOM_RECTS[room.id]);
      expect(roomAt(x, z)).toBe(room.id);
    }
    expect(roomAt(-1, -1)).toBeNull();
  });

  it('reaches every open room through open doors, and no locked room at all', () => {
    const open = ROOMS.filter((room) => !isLocked(room)).map((room) => room.id);
    const links = doorLinks('inner');
    expect(links.flat()).not.toContain(null);
    const reached = new Set([open[0]]);
    for (let pass = 0; pass < open.length; pass += 1) {
      for (const [a, b] of links) {
        if (reached.has(a ?? undefined)) reached.add(b ?? undefined);
        if (reached.has(b ?? undefined)) reached.add(a ?? undefined);
      }
    }
    expect([...reached].sort()).toEqual([...open].sort());
    for (const [a, b] of doorLinks('locked')) {
      expect(ROOMS.find((room) => room.id === b)?.opensWith).not.toBeNull();
      expect(ROOMS.find((room) => room.id === a)?.opensWith).toBeNull();
    }
  });

  it('cuts a door-wide gap for each open door and none for a closed one', () => {
    const inner = WALL_LINES.find((line) => line.kind === 'inner' && line.doors.length === 4);
    const locked = WALL_LINES.find((line) => line.kind === 'locked' && line.doors.length > 0);
    expect(inner && wallSegments(inner)).toEqual([
      [0, 4 - DOOR_WIDTH / 2],
      [4 + DOOR_WIDTH / 2, 12.5 - DOOR_WIDTH / 2],
      [12.5 + DOOR_WIDTH / 2, 19.5 - DOOR_WIDTH / 2],
      [19.5 + DOOR_WIDTH / 2, 28 - DOOR_WIDTH / 2],
      [28 + DOOR_WIDTH / 2, 32],
    ]);
    expect(locked && wallSegments(locked)).toEqual([[0, 32]]);
  });

  it('stands the two outer walls behind the camera tall at each yaw', () => {
    const far = (yaw: number) =>
      (['north', 'west', 'south', 'east'] as const).filter((side) => isFarWall(side, yaw));
    expect(far(45)).toEqual(['north', 'west']);
    expect(far(135)).toEqual(['west', 'south']);
    expect(far(225)).toEqual(['south', 'east']);
    expect(far(315)).toEqual(['north', 'east']);
  });

  it('seats every agent in its own room, and each connector in the Data Dock', () => {
    const seats = seatsFor(roster);
    expect([...seats.keys()]).toEqual(roster.map((agent) => agent.id));
    for (const agent of roster) {
      const seat = seats.get(agent.id);
      expect(seat && roomAt(seat.x, seat.z)).toBe(agent.room);
    }
    const places = [...seats.values()].map((seat) => `${seat.x},${seat.z}`);
    expect(new Set(places).size).toBe(places.length);
  });

  it('fits any number of connectors into the loading bay', () => {
    expect(connectorSeat(0, 1)).toEqual({ x: 1.3, z: 2.2, facing: 0, pose: 'stand' });
    const many = Array.from({ length: 12 }, (_, index) => connectorSeat(index, 12));
    for (const seat of many)
      expect(inRect(ROOM_RECTS['data-dock'], seat.x, seat.z, 0.5)).toBe(true);
    expect(new Set(many.map((seat) => `${seat.x},${seat.z}`)).size).toBe(12);
    expect(connectorProps(connectorSeat(0, 1))[0]).toMatchObject({
      kind: 'crateStack',
      room: 'data-dock',
    });
  });

  it('puts every piece of furniture and every sign inside its room', () => {
    for (const item of FURNITURE) {
      expect(`${item.kind} ${roomAt(item.x, item.z)}`).toBe(`${item.kind} ${item.room}`);
      expect(inRect(ROOM_RECTS[item.room], item.x, item.z, 0.3)).toBe(true);
    }
    for (const room of ROOMS) {
      const [x, z] = ROOM_LABEL_POINTS[room.id];
      expect(roomAt(x, z)).toBe(room.id);
    }
  });
});

describe('the camera (§9.8)', () => {
  it('starts at 45° and turns in 90° steps, both ways', () => {
    expect([0, 1, 2, 3, 4, -1].map(yawDegrees)).toEqual([45, 135, 225, 315, 45, 315]);
  });

  it('has three zoom stops, each with its pixel size, scaled by the device pixel ratio', () => {
    expect(ZOOM_STOPS).toHaveLength(3);
    expect([clampZoom(-3), clampZoom(1.4), clampZoom(9)]).toEqual([0, 1, 2]);
    expect(pixelSize(0, 1)).toBe(3);
    expect(pixelSize(0, 2)).toBe(6);
    expect(pixelSize(2, 1)).toBe(5);
    expect(pixelSize(0, 0.1)).toBe(1);
    expect(cellCssPixels(1)).toBe(4);
    expect(zoomScale(2)).toBe(2.25);
    expect(EDGE_STRENGTH).toEqual({ normal: 0.3, depth: 0.4 });
  });

  it('builds an orthonormal basis looking down at 35°', () => {
    const basis = cameraBasis(45);
    for (const axis of [basis.right, basis.up, basis.back]) expect(dot(axis, axis)).toBeCloseTo(1);
    expect(dot(basis.right, basis.up)).toBeCloseTo(0);
    expect(dot(basis.up, basis.back)).toBeCloseTo(0);
    expect(Math.asin(basis.back[1]) * (180 / Math.PI)).toBeCloseTo(35);
    expect(cameraBasis(0).back).toEqual([
      0,
      Math.sin((35 * Math.PI) / 180),
      Math.cos((35 * Math.PI) / 180),
    ]);
    const target: Vec3 = [16, 0, 10];
    const position = cameraPosition(target, basis);
    expect(Math.hypot(position[0] - 16, position[1], position[2] - 10)).toBeCloseTo(
      CAMERA_DISTANCE,
    );
  });

  it('fits the office into the viewport with a margin', () => {
    const extent = projectedExtent(FLOOR, 2.4, cameraBasis(45));
    expect(extent.width).toBeCloseTo((FLOOR.width + FLOOR.depth) * Math.SQRT1_2);
    const fit = fitPixelsPerUnit({ width: 1280, height: 700 }, extent);
    expect(extent.width * fit).toBeLessThanOrEqual(1280);
    expect(extent.height * fit).toBeLessThanOrEqual(700);
    expect(fitPixelsPerUnit({ width: 0, height: 700 }, extent)).toBe(1);
  });

  it('snaps the target to whole cells across and up the screen, keeping its depth', () => {
    const basis = cameraBasis(45);
    const target: Vec3 = [16.123, 0, 10.456];
    const snapped = snapTarget(target, basis, 0.1);
    for (const axis of [basis.right, basis.up]) {
      const cells = dot(snapped, axis) / 0.1;
      expect(cells).toBeCloseTo(Math.round(cells), 6);
      expect(Math.abs(dot(snapped, axis) - dot(target, axis))).toBeLessThanOrEqual(0.05 + 1e-9);
    }
    expect(dot(snapped, basis.back)).toBeCloseTo(dot(target, basis.back));
    expect(snapTarget(target, basis, 0)).toBe(target);
  });

  it('moves the floor with a drag, and keeps the target over the floor', () => {
    const basis = cameraBasis(45);
    const start: Vec3 = [16, 0, 10];
    const moved = panTarget(start, basis, 100, 0, 50);
    expect(dot(moved, basis.right) - dot(start, basis.right)).toBeCloseTo(-2);
    const lifted = panTarget(start, basis, 0, 50, 50);
    expect(lifted[1]).toBe(0);
    expect(dot(lifted, basis.up) - dot(start, basis.up)).toBeCloseTo(1);
    expect(clampTarget([-5, 3, 99], FLOOR)).toEqual([0, 0, FLOOR.depth]);
    expect(clampTarget([40, 0, 5], FLOOR)).toEqual([FLOOR.width, 0, 5]);
  });
});

describe("the agents' looks (§9.3, §9.4)", () => {
  it('glows only while WORKING or in HANDOFF, and pairs every colour with a glyph', () => {
    const glowing = (Object.keys(LOOKS) as AgentState[]).filter((state) => LOOKS[state].glow);
    expect(glowing).toEqual(['WORKING', 'HANDOFF']);
    const glyphs = Object.values(LOOKS).map((look) => look.glyph);
    expect(new Set(glyphs).size).toBe(glyphs.length);
  });

  it('combines readiness: a failure first, then loading, then ready with a pending count', () => {
    expect(
      combine({ kind: 'ready' }, { kind: 'failed', reason: 'x' }, { kind: 'loading' }),
    ).toEqual({
      kind: 'failed',
      reason: 'x',
    });
    expect(combine({ kind: 'ready' }, { kind: 'loading' })).toEqual({ kind: 'loading' });
    expect(combine({ kind: 'ready', pendingBriefs: 2 }, { kind: 'ready' })).toEqual({
      kind: 'ready',
      pendingBriefs: 2,
    });
    expect(combine()).toEqual({ kind: 'ready' });
  });

  it('never makes an agent WORKING in the static office (D-F-1)', () => {
    expect(officeStatus({ kind: 'loading' })).toEqual({
      state: 'IDLE',
      bubble: 'loading',
      detail: 'Loading its data…',
    });
    expect(officeStatus({ kind: 'failed', reason: 'down' })).toEqual({
      state: 'ERROR',
      bubble: null,
      detail: 'down',
    });
    expect(officeStatus({ kind: 'ready' })).toEqual({
      state: 'IDLE',
      bubble: null,
      detail: 'Idle',
    });
    expect(officeStatus({ kind: 'ready', pendingBriefs: 1 })).toMatchObject({
      state: 'WAITING',
      bubble: 'waiting',
      detail: '1 brief awaits your decision',
    });
    expect(officeStatus({ kind: 'ready', pendingBriefs: 3 }).detail).toBe(
      '3 briefs await your decision',
    );
  });

  it("points a ticket at SUPPORT_AGENT's desk and a document at LINKER_AGENT's (§8.4)", () => {
    expect(evidenceDesk('support_tickets')).toBe('support');
    expect(evidenceDesk('documents')).toBe('linker');
    expect(evidenceDesk('deals')).toBeNull();
    expect(FIXED_AGENTS.map((agent) => agent.id)).toEqual(
      expect.arrayContaining(['support', 'linker']),
    );
  });
});

describe("SIGNALS_AGENT's board (§9.2)", () => {
  const detail = loadExchanges('assessment-details.json')[0]?.body as AssessmentDetail;

  it("shows the recorded CUST-007 assessment's signals and band", () => {
    const board = signalsBoard(detail.customer_source_id, detail.band, signalRows(detail.signals));
    expect(board.title).toBe(`SIGNALS ${detail.customer_source_id ?? ''}`);
    expect(board.footer).toBe('BAND CRITICAL');
    expect(board.band).toBe('CRITICAL');
    expect(board.cells.map((cell) => [cell.id, cell.value])).toEqual(
      signalRows(detail.signals).map((row) => [row.id, row.value]),
    );
    expect(board.cells.every((cell) => Array.from(cell.shown).length <= BOARD_VALUE_WIDTH)).toBe(
      true,
    );
  });

  it('clips a long value on the board only, by code points', () => {
    expect(clip('performance', 11)).toBe('performance');
    expect(clip('performances', 11)).toBe('performanc…');
    expect(clip('😀😀😀', 2)).toBe('😀…');
    const board = signalsBoard(null, 'NONE', [
      { id: 'S10', key: 'dominant_ticket_category', value: 'x'.repeat(20) },
    ]);
    expect(board.title).toBe('SIGNALS');
    expect(board.cells[0]).toMatchObject({ value: 'x'.repeat(20), shown: `${'x'.repeat(10)}…` });
  });

  it('splits the cells into two columns, the first taking the extra one', () => {
    const cells = signalsBoard(null, 'NONE', signalRows(detail.signals)).cells;
    const [left, right] = boardColumns(cells);
    expect(left).toHaveLength(Math.ceil(cells.length / 2));
    expect([...left, ...right]).toEqual(cells);
  });
});

describe('seeds (§9.7)', () => {
  it('hashes a string the same way every time, and differently for different strings', () => {
    expect(hashString('memory')).toBe(hashString('memory'));
    expect(hashString('memory')).not.toBe(hashString('linker'));
    expect(hashString('')).toBe(0x811c9dc5);
  });

  it('generates the same numbers in [0, 1) from the same seed', () => {
    const first = seededRandom(7);
    const second = seededRandom(7);
    const values = Array.from({ length: 50 }, () => first());
    expect(values).toEqual(Array.from({ length: 50 }, () => second()));
    expect(values.every((value) => value >= 0 && value < 1)).toBe(true);
    expect(pick(['a', 'b', 'c'], 4)).toBe('b');
  });
});

describe('the performance record (§9.10)', () => {
  const samples: FrameSample[] = Array.from({ length: 100 }, (_, index) => ({
    at: 1000 + index * 16,
    frameMs: index < 95 ? 16 : 30,
    drawCalls: 60 + (index % 3),
    triangles: 5000 + index,
  }));

  it('takes nearest-rank percentiles', () => {
    expect(percentile([], 50)).toBeNaN();
    expect(percentile([5, 1, 3], 50)).toBe(3);
    expect(percentile([5, 1, 3], 0)).toBe(1);
    expect(percentile([5, 1, 3], 100)).toBe(5);
  });

  it('keeps the last 30 seconds', () => {
    expect(recent(samples, 1000 + 99 * 16, 160)).toHaveLength(11);
  });

  it('summarises frame times and draw calls against the budget', () => {
    const summary = summarize(samples);
    expect(summary).toMatchObject({
      frames: 100,
      spanMs: 99 * 16,
      medianMs: 16,
      p95Ms: 16,
      maxDrawCalls: 62,
      medianDrawCalls: 61,
      maxTriangles: 5099,
      within: true,
    });
    expect(summarize([])).toBeNull();
    const slow = samples.map((sample) => ({ ...sample, frameMs: 40 }));
    expect(summarize(slow)?.within).toBe(false);
    const busy = samples.map((sample) => ({ ...sample, drawCalls: PERF_BUDGET.drawCalls + 1 }));
    expect(summarize(busy)?.within).toBe(false);
    const jittery = samples.map((sample, index) => ({
      ...sample,
      frameMs: index % 10 === 0 ? 30 : 16,
    }));
    expect(summarize(jittery)?.within).toBe(false);
    // A 16.7 ms frame measured as a difference of timestamps is within; 16.71 ms is not.
    const noisy = samples.map((sample) => ({ ...sample, frameMs: 5000.1 - 4983.4 }));
    expect(noisy[0]?.frameMs).toBeGreaterThan(PERF_BUDGET.medianMs);
    expect(summarize(noisy)?.within).toBe(true);
    const over = samples.map((sample) => ({ ...sample, frameMs: 16.71 }));
    expect(summarize(over)?.within).toBe(false);
  });
});
