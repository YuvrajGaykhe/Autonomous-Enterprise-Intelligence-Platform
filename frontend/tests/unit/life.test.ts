/**
 * F4's pure modules (spec §9.4–§9.7, AC-F-1, AC-F-2; the owner's F4 ruling on motion): the walk
 * grid, the Break Area, ambient life, episodes from the recorded fixtures, the Director and walks.
 */

import { describe, expect, it } from 'vitest';

import { briefPayloadV1 } from '@/api/schemas/briefPayloadV1';
import type { IngestionRunCreatedResponse } from '@/api/schemas/operations';
import type { AssessmentListItem, BriefResponse } from '@/api/schemas/risk';
import { AmbientPlanner } from '@/domain/ambient';
import { BREAK_SPOTS, suits } from '@/domain/breakArea';
import {
  BEATS,
  frameAt,
  holdTimeline,
  liveTimeline,
  nextChange,
  placeSeat,
  replayTimeline,
  shownTexts,
  type Timeline,
} from '@/domain/director';
import {
  assessmentEpisode,
  entityCaption,
  ingestionEpisode,
  participants,
  type Episode,
} from '@/domain/episodes';
import {
  DEBATE_SEATS,
  FURNITURE,
  ROOM_RECTS,
  debateSeat,
  inRect,
  officeFurniture,
  roomAt,
  visitPoint,
} from '@/domain/floorPlan';
import { groupSnapshots, inboxRows, type Snapshot } from '@/domain/inbox';
import { BREAK_MIDDLE, gatherSeconds, officeLayout } from '@/domain/layout';
import { rosterFor } from '@/domain/roster';
import {
  CELL,
  FOOTPRINTS,
  FREE,
  FURNITURE_CELL,
  WALK_SPEED,
  WALL_CELL,
  buildWalkGrid,
  clearLine,
  findPath,
  footprintBox,
  isFree,
  markOpenFloor,
  nearestFreeCell,
  pathLength,
  walkSeconds,
  type Point,
  type WalkGrid,
} from '@/domain/walkGrid';
import {
  HURRY,
  TURN_RATE,
  advance,
  arrived,
  headingOf,
  paceFor,
  remaining,
  turnBetween,
  turnTowards,
  type Mover,
} from '@/domain/walker';

import {
  allRecordedBriefs,
  autoRun,
  loadExchanges,
  recordedAssessmentList,
  recordedBody,
} from '../support/fixtures';

const sources = recordedBody<{ sources: { source: string }[] }>(
  'sources.json',
  'GET',
  '/api/v1/sources',
).sources;
const roster = rosterFor(sources);
const layout = officeLayout(roster);
const grid = layout.grid;
const at = (seat: { x: number; z: number }): Point => [seat.x, seat.z];

// ---------------------------------------------------------------------------------------------
// Fixtures as the page would hold them.

const briefBodies = allRecordedBriefs().map((exchange) => exchange.body as BriefResponse);
const briefsById = new Map(briefBodies.map((brief) => [brief.id, brief]));

function snapshotAt(items: readonly AssessmentListItem[]): Snapshot {
  const [snapshot] = groupSnapshots(items);
  if (snapshot === undefined) throw new Error('no snapshot');
  return snapshot;
}

function episodeFor(asOf: string, items: AssessmentListItem[], featuredIndex = 0): Episode {
  const snapshot = snapshotAt(items);
  const rows = inboxRows(snapshot, briefsById, new Map());
  const row = rows[featuredIndex];
  const brief = row === undefined ? undefined : briefsById.get(row.briefId);
  return assessmentEpisode({
    asOf,
    list: items,
    snapshot,
    rows,
    featured:
      brief === undefined
        ? null
        : { briefId: brief.id, payload: briefPayloadV1.parse(brief.payload) },
  });
}

const list0918 = recordedAssessmentList<{ items: AssessmentListItem[] }>().items;
const autoList = autoRun().find((exchange) => exchange.path.startsWith('/api/v1/risk/assessments?'))
  ?.body as { items: AssessmentListItem[] };

/** The recorded body behind a step's route. */
function bodyOf(route: string): unknown {
  const [method, path] = route.split(' ') as ['GET' | 'POST', string];
  if (path.startsWith('/api/v1/risk/assessments?as_of=')) {
    const asOf = path.split('=')[1];
    if (asOf === '2026-09-18') return recordedAssessmentList<unknown>();
    return autoList;
  }
  if (path.startsWith('/api/v1/risk/briefs/')) {
    return allRecordedBriefs().find((exchange) => exchange.path === path)?.body;
  }
  if (method === 'POST' && path === '/api/v1/ingestion/runs') {
    return loadExchanges('ingestion-run.json').find((exchange) => exchange.method === 'POST')?.body;
  }
  throw new Error(`no fixture for ${route}`);
}

/** A JSON path's values: `a.b[2].c`, with `[*]` for every item and `[1,4]` for some. */
function resolvePath(body: unknown, path: string): unknown[] {
  let values: unknown[] = [body];
  for (const part of path.match(/[^.[\]]+|\[[^\]]*\]/g) ?? []) {
    if (part.startsWith('[')) {
      const inner = part.slice(1, -1);
      values = values.flatMap((value) => {
        const items = value as unknown[];
        return inner === '*' ? items : inner.split(',').map((index) => items[Number(index)]);
      });
    } else {
      values = values.map((value) => (value as Record<string, unknown> | undefined)?.[part]);
    }
  }
  return values;
}

function expectSourcesResolve(episode: Episode): void {
  for (const step of episode.steps) {
    const values = resolvePath(bodyOf(step.source.route), step.source.path);
    expect(values.length, `${step.caption}: ${step.source.path}`).toBeGreaterThan(0);
    expect(values, `${step.caption}: ${step.source.path}`).not.toContain(undefined);
  }
}

// ---------------------------------------------------------------------------------------------

describe('the walk grid (§9.7)', () => {
  it('blocks walls but leaves open doors, and keeps the locked rooms shut', () => {
    // A wall between the Data Dock and the Evidence Lab, and its door at z = 5.
    expect(isFree(grid, [10, 2])).toBe(false);
    expect(isFree(grid, [10, 5])).toBe(true);
    // The locked row's closed door.
    expect(isFree(grid, [4, 15])).toBe(false);
    // Inside a locked room there is no open floor at all.
    expect(isFree(grid, [4, 17.5])).toBe(false);
    expect(nearestFreeCell(grid, [4, 17.5])).toBeNull();
    expect(findPath(grid, BREAK_MIDDLE, [4, 17.5])).toBeNull();
    expect(walkSeconds(grid, BREAK_MIDDLE, [4, 17.5])).toBe(0);
  });

  it('blocks what furniture stands on, grown by an agent’s reach, and not a rug', () => {
    const desk = FURNITURE.find((item) => item.kind === 'desk');
    const rug = FURNITURE.find((item) => item.kind === 'rug');
    expect(desk && isFree(grid, [desk.x, desk.z])).toBe(false);
    expect(rug && isFree(grid, [rug.x + 1.5, rug.z + 1])).toBe(true);
    const walkable = Object.entries(FOOTPRINTS).filter(([, size]) => size === null);
    expect(walkable.map(([kind]) => kind)).toContain('rug');
    expect(footprintBox({ kind: 'rug', x: 1, z: 1, rotation: 0, room: 'ceo-office' })).toBeNull();
  });

  it('turns a footprint with its item', () => {
    const item = { kind: 'sofa', x: 10, z: 10, rotation: Math.PI / 2, room: 'break-area' } as const;
    const [x0, z0, x1, z1] = footprintBox(item) ?? [0, 0, 0, 0];
    expect(x1 - x0).toBeCloseTo(0.85);
    expect(z1 - z0).toBeCloseTo(2.1);
  });

  it('finds a walk from the Break Area to every desk, visit point, debate seat and place', () => {
    const targets: Point[] = [
      ...[...layout.seats.values()].map(at),
      ...roster.map((agent) =>
        at(visitPoint(agent.kind, layout.seats.get(agent.id) ?? DEBATE_SEATS[0]!)),
      ),
      ...DEBATE_SEATS.map(at),
      ...BREAK_SPOTS.map(at),
    ];
    for (const target of targets) {
      const path = findPath(grid, BREAK_MIDDLE, target);
      expect(path, `${target.join(',')}`).not.toBeNull();
      if (path === null) continue;
      expect(path[0]).toEqual(BREAK_MIDDLE);
      expect(path.at(-1)).toEqual(target);
      // Between its first and last steps the walk stays on the open floor.
      for (let index = 2; index < path.length - 1; index += 1)
        expect(clearLine(grid, path[index - 1] as Point, path[index] as Point)).toBe(true);
    }
  });

  it('walks straight across open floor, and not at all to where it stands', () => {
    expect(findPath(grid, [27, 11], [27, 12])).toEqual([
      [27, 11],
      [27, 12],
    ]);
    expect(findPath(grid, [27, 11], [27, 11])).toEqual([
      [27, 11],
      [27, 11],
    ]);
    expect(
      pathLength([
        [0, 0],
        [3, 4],
        [3, 5],
      ]),
    ).toBe(6);
    expect(walkSeconds(grid, [27, 11], [27, 12])).toBeCloseTo(1 / WALK_SPEED);
  });

  it('goes through doors rather than walls', () => {
    const path = findPath(grid, at(layout.seats.get('memory')!), at(layout.seats.get('linker')!));
    expect(path).not.toBeNull();
    const length = pathLength(path ?? []);
    expect(length).toBeGreaterThan(Math.hypot(13.5 - 7.9, 3.4 - 2.6));
    expect(path?.some(([x, z]) => Math.abs(x - 10) < 1 && Math.abs(z - 5) < 1.2)).toBe(true);
  });

  it('walks between two points of one cell without a detour', () => {
    expect(findPath(grid, [27.01, 11.01], [27.2, 11.2])).toEqual([
      [27.01, 11.01],
      [27.2, 11.2],
    ]);
  });

  /** A small hand-made floor: `.` free, `#` furniture, `|` wall. */
  function floor(rows: string[]): WalkGrid {
    const cells = rows.flatMap((row) =>
      [...row].map((cell) => (cell === '.' ? FREE : cell === '#' ? FURNITURE_CELL : WALL_CELL)),
    );
    const made: WalkGrid = {
      columns: rows[0]?.length ?? 0,
      rows: rows.length,
      cells: Uint8Array.from(cells),
      open: new Uint8Array(cells.length),
    };
    markOpenFloor(made);
    return made;
  }
  const middleOf = (column: number, row: number): Point => [
    (column + 0.5) * CELL,
    (row + 0.5) * CELL,
  ];

  it('walks up to the very edge of a floor with no walls round it', () => {
    const open = floor(['....', '....', '....']);
    const path = findPath(open, middleOf(0, 0), middleOf(3, 2));
    expect(path).toEqual([middleOf(0, 0), middleOf(3, 2)]);
    const around = floor(['.....', '.###.', '.....']);
    const long = findPath(around, middleOf(0, 1), middleOf(4, 1));
    expect(long?.length).toBeGreaterThan(2);
    expect(nearestFreeCell(floor(['..#']), middleOf(2, 0))).toBe(1);
  });

  it('keeps only the largest free region as open floor, and finds no walk out of the rest', () => {
    const split = floor(['...|..', '...|..']);
    expect(isFree(split, middleOf(0, 0))).toBe(true);
    expect(isFree(split, middleOf(5, 0))).toBe(false);
    // Marked open by hand, the small region still has no walk to the large one.
    split.open[5] = 1;
    expect(findPath(split, middleOf(0, 0), middleOf(5, 0))).toBeNull();
  });

  it('sizes its cells to the floor', () => {
    expect(grid.columns * CELL).toBe(32);
    expect(grid.rows * CELL).toBe(20);
    const bare = buildWalkGrid([]);
    expect(isFree(bare, [5, 5])).toBe(true);
    expect(officeFurniture(roster).length).toBe(FURNITURE.length + 3);
  });
});

describe('the Break Area (the owner’s F4 ruling)', () => {
  it('has a place for every agent with a body, each inside the Break Area, each its own', () => {
    const bodies = roster.filter((agent) => agent.kind !== 'ceo');
    expect(BREAK_SPOTS.length).toBeGreaterThanOrEqual(bodies.length + 4);
    expect(new Set(BREAK_SPOTS.map((spot) => spot.id)).size).toBe(BREAK_SPOTS.length);
    expect(new Set(BREAK_SPOTS.map((spot) => `${spot.x},${spot.z}`)).size).toBe(BREAK_SPOTS.length);
    for (const spot of BREAK_SPOTS) {
      expect(roomAt(spot.x, spot.z)).toBe('break-area');
      expect(inRect(ROOM_RECTS['break-area'], spot.x, spot.z, 0.3)).toBe(true);
    }
  });

  it('keeps MEMORY on its feet and the charging pad for MEMORY', () => {
    const charger = BREAK_SPOTS.find((spot) => spot.activity === 'charge');
    const seat = BREAK_SPOTS.find((spot) => spot.pose === 'sit');
    expect(charger && suits('memory', charger)).toBe(true);
    expect(charger && suits('sales', charger)).toBe(false);
    expect(seat && suits('memory', seat)).toBe(false);
    expect(seat && suits('linker', seat)).toBe(true);
  });

  it('has more to do than F3’s: games, a lounge, a kitchenette and a café corner', () => {
    const kinds = new Set(
      FURNITURE.filter((item) => item.room === 'break-area').map((item) => item.kind),
    );
    for (const kind of [
      'arcadeCabinet',
      'pingPongTable',
      'tvConsole',
      'sofa',
      'armchair',
      'beanBag',
      'fridge',
      'coffeeMachine',
      'waterCooler',
      'vendingMachine',
      'cafeTable',
      'chargingPad',
    ] as const)
      expect(kinds.has(kind), kind).toBe(true);
  });
});

describe('ambient life (§9.7)', () => {
  const bodies = roster.filter((agent) => agent.kind !== 'ceo');

  it('hands out the same places in the same order, never one place to two agents', () => {
    const first = new AmbientPlanner(null);
    const second = new AmbientPlanner(null);
    const a = bodies.map((agent) => first.spotFor(agent.id, agent.kind, 0)?.id);
    const b = bodies.map((agent) => second.spotFor(agent.id, agent.kind, 0)?.id);
    expect(a).toEqual(b);
    expect(new Set(a).size).toBe(bodies.length);
    expect(a).not.toContain(undefined);
    expect([...first.holders().values()].sort()).toEqual(bodies.map((agent) => agent.id).sort());
  });

  it('never moves an agent on when still', () => {
    const planner = new AmbientPlanner(null);
    const spot = planner.spotFor('linker', 'linker', 0);
    planner.arrived('linker', 0);
    expect(planner.spotFor('linker', 'linker', 10_000)).toBe(spot);
  });

  it('moves an agent on after its dwell, counted from its arrival, to another free place', () => {
    const planner = new AmbientPlanner([5, 5]);
    const spot = planner.spotFor('linker', 'linker', 0);
    // Walking there takes as long as it takes: no dwell is counted before it arrives.
    expect(planner.spotFor('linker', 'linker', 100)).toBe(spot);
    planner.arrived('linker', 100);
    planner.arrived('linker', 200);
    expect(planner.spotFor('linker', 'linker', 104)).toBe(spot);
    const next = planner.spotFor('linker', 'linker', 105);
    expect(next).not.toBe(spot);
    expect(planner.holders().get(next?.id ?? '')).toBe('linker');
    expect(planner.holders().has(spot?.id ?? '')).toBe(false);
  });

  it('frees a place when its agent goes to work, and keeps MEMORY off the seats', () => {
    const planner = new AmbientPlanner(null);
    const spot = planner.spotFor('memory', 'memory', 0);
    expect(spot?.pose).toBe('stand');
    planner.release('memory');
    planner.release('nobody');
    expect(planner.holders().size).toBe(0);
  });

  it('says so when no place is free, and keeps an agent where it is', () => {
    const only = [BREAK_SPOTS[0]!];
    const planner = new AmbientPlanner([0, 0], only);
    expect(planner.spotFor('a', 'sales', 0)).toBe(only[0]);
    expect(planner.spotFor('b', 'sales', 0)).toBeNull();
    planner.arrived('a', 0);
    expect(planner.spotFor('a', 'sales', 1)).toBe(only[0]);
    planner.arrived('nobody', 0);
  });
});

describe('episodes from the recorded fixtures (§9.5, AC-F-1)', () => {
  const cust007 = episodeFor('2026-09-18', list0918, 0);

  it('plays every stage for CUST-007, each caption from its data path', () => {
    expectSourcesResolve(cust007);
    const captions = cust007.steps.map(
      (step) => `${step.stage} ${step.agents.join('+')} ${step.caption}`,
    );
    expect(captions).toEqual([
      '1 memory SNAPSHOT 1d891b0b',
      '2 linker 6 LINKS · CUST-007',
      '3 signals 1 CRITICAL · 2 WATCH · 47 NONE',
      '4 sales ACCELERATE_DEAL_CLOSE',
      '4 support ASSIGN_DEDICATED_SUPPORT_OWNER',
      '5 sales+support CONFLICT DEAL-001',
      '6 reconciler CONF-001 → SUPPORT PREVAILS',
      '7 brief-writer BRIEF CUST-007',
      '7 brief-writer BRIEF CUST-025',
      '7 brief-writer BRIEF CUST-036',
      '8 ceo 3 IN TRAY',
    ]);
    expect(
      cust007.steps.filter((step) => step.kind === 'deliver').map((step) => step.tray),
    ).toEqual([1, 2, 3]);
    expect(participants(cust007)).toEqual([
      'memory',
      'linker',
      'signals',
      'sales',
      'support',
      'reconciler',
      'brief-writer',
    ]);
  });

  it('checks each caption against the value its path reads', () => {
    for (const step of cust007.steps) {
      const values = resolvePath(bodyOf(step.source.route), step.source.path);
      if (step.stage === 1) expect(step.caption).toContain(String(values[0]).slice(0, 8));
      if (step.stage === 2)
        expect(step.caption).toContain(`${(values[0] as unknown[]).length} LINKS`);
      if (step.stage === 3) expect(values).toHaveLength(list0918.length);
      if (step.stage === 4 || step.stage === 5 || step.stage === 6 || step.stage === 7)
        expect(step.caption).toContain(String(values[0]));
    }
  });

  it('emits no step without its data: a brief with no links, no conflict, no position', () => {
    const cust025 = episodeFor('2026-09-18', list0918, 1);
    const cust036 = episodeFor('2026-09-18', list0918, 2);
    for (const episode of [cust025, cust036]) {
      expectSourcesResolve(episode);
      expect(episode.steps.some((step) => step.kind === 'conflict')).toBe(false);
      expect(episode.steps.some((step) => step.stage === 2)).toBe(false);
      expect(episode.steps.some((step) => step.stage === 6)).toBe(false);
    }
    expect(cust025.steps.filter((step) => step.stage === 4).map((step) => step.agents)).toEqual([
      ['support'],
    ]);
    expect(cust036.steps.some((step) => step.stage === 4)).toBe(false);
  });

  it('plays the Auto run’s snapshot too, with its four briefs', () => {
    const episode = episodeFor('2026-08-27', autoList.items);
    expectSourcesResolve(episode);
    expect(episode.steps.filter((step) => step.kind === 'deliver')).toHaveLength(4);
  });

  it('plays nothing for an empty snapshot, and no brief without a featured one', () => {
    const empty = assessmentEpisode({
      asOf: '2026-09-18',
      list: [],
      snapshot: { id: 'none', key: snapshotAt(list0918).key, items: [] },
      rows: [],
      featured: null,
    });
    expect(empty.steps).toEqual([]);
    const noBrief = assessmentEpisode({
      asOf: '2026-09-18',
      list: list0918,
      snapshot: snapshotAt(list0918),
      rows: [],
      featured: null,
    });
    expect(noBrief.steps.map((step) => step.stage)).toEqual([1, 3]);
  });

  it('names a snapshot that is part of the list by its own items', () => {
    const snapshot = snapshotAt(list0918);
    const part = { ...snapshot, items: snapshot.items.slice(0, 2) };
    const episode = assessmentEpisode({
      asOf: '2026-09-18',
      list: list0918,
      snapshot: part,
      rows: [],
      featured: null,
    });
    expect(episode.steps.find((step) => step.stage === 3)?.source.path).toBe('items[0,1].band');
    expectSourcesResolve(episode);
  });

  it('delivers a brief without a customer under its brief id', () => {
    const snapshot = snapshotAt(list0918);
    const rows = inboxRows(snapshot, briefsById, new Map()).map((row) => ({
      ...row,
      customerId: null,
    }));
    const episode = assessmentEpisode({
      asOf: '2026-09-18',
      list: list0918,
      snapshot,
      rows,
      featured: null,
    });
    const delivery = episode.steps.find((step) => step.kind === 'deliver');
    expect(delivery?.caption).toBe(`BRIEF ${rows[0]?.briefId.slice(0, 8)}`);
    expect(delivery?.source.path).toMatch(/\.brief_ids$/);
    expectSourcesResolve(episode);
  });

  it('carries an ingestion run’s own outcome to MEMORY, entity by entity', () => {
    const run = loadExchanges('ingestion-run.json').find((exchange) => exchange.method === 'POST')
      ?.body as IngestionRunCreatedResponse;
    const episode = ingestionEpisode('csv_demo', run);
    expectSourcesResolve(episode);
    expect(episode.steps[0]).toMatchObject({
      kind: 'handoff',
      agents: ['csv_demo'],
      to: 'memory',
      caption: `${run.status} · ${run.records_fetched} FETCHED`,
    });
    expect(episode.steps.slice(1).map((step) => step.caption)).toEqual(
      run.entities.map(entityCaption),
    );
    expect(participants(episode)).toEqual(['csv_demo', 'memory']);
  });

  it('words each entity’s counts, and says when it was skipped or failed', () => {
    const entity = {
      entity_type: 'deals',
      status: 'completed',
      records_fetched: 5,
      records_inserted: 1,
      records_updated: 2,
      records_unchanged: 2,
      records_rejected: 0,
      records_failed: 0,
      warnings: 0,
      batches_committed: 1,
      batches_failed: 0,
      failure: null,
    } as const;
    expect(entityCaption(entity)).toBe('DEALS: 1 NEW · 2 UPDATED · 2 UNCHANGED');
    expect(entityCaption({ ...entity, records_rejected: 3, records_failed: 1 })).toBe(
      'DEALS: 1 NEW · 2 UPDATED · 2 UNCHANGED · 3 REJECTED · 1 FAILED',
    );
    expect(entityCaption({ ...entity, status: 'skipped' })).toBe('DEALS: SKIPPED');
    expect(entityCaption({ ...entity, status: 'failed' })).toBe('DEALS: FAILED');
  });
});

describe('the Director (§9.4–§9.6, D-F-1, AC-F-2)', () => {
  const episode = episodeFor('2026-09-18', list0918, 0);
  const gather = gatherSeconds(layout, participants(episode));
  const timeline = replayTimeline(episode, layout, gather);
  const captions = new Set(episode.steps.map((step) => step.caption));

  /** Every frame at every change, and the states it holds. */
  function frames(line: Timeline): { t: number; frame: ReturnType<typeof frameAt> }[] {
    const result = [];
    let t = 0;
    while (t < line.duration && result.length < 500) {
      result.push({ t, frame: frameAt(line, t) });
      t = nextChange(line, t);
    }
    result.push({ t, frame: frameAt(line, t) });
    return result;
  }

  it('shows only the episode’s own captions and labels', () => {
    for (const text of shownTexts(timeline)) expect(captions.has(text), text).toBe(true);
    for (const { frame } of frames(timeline))
      for (const [, directive] of frame.directives)
        if (directive.state === 'WORKING' || directive.state === 'HANDOFF')
          if (directive.caption !== null) expect(captions.has(directive.caption)).toBe(true);
  });

  it('gathers everyone at their desks first, idle, and ends with everyone done', () => {
    const start = frameAt(timeline, 0);
    expect([...start.directives.keys()]).toEqual(participants(episode));
    for (const directive of start.directives.values())
      expect(directive).toMatchObject({ state: 'IDLE', place: { kind: 'desk' }, arriveBy: gather });
    const last = frameAt(timeline, timeline.duration - 0.01);
    for (const directive of last.directives.values())
      expect(directive).toMatchObject({ state: 'DONE', cheer: true });
    const after = frameAt(timeline, timeline.duration);
    expect(after).toMatchObject({ ended: true, arrows: [], trayCount: null });
    expect(after.directives.size).toBe(0);
    expect(nextChange(timeline, timeline.duration)).toBe(Infinity);
  });

  it('works each step at the desk, in stage order, and walks each result to the next stage', () => {
    const seen: string[] = [];
    for (const { frame } of frames(timeline))
      for (const [agent, directive] of frame.directives) {
        const entry = `${agent} ${directive.state} ${directive.place.kind}`;
        if (
          directive.state !== 'IDLE' &&
          directive.state !== 'DONE' &&
          seen.at(-1) !== entry &&
          !seen.includes(entry)
        )
          seen.push(entry);
      }
    expect(seen).toEqual([
      'memory WORKING desk',
      'memory HANDOFF visit',
      'linker WORKING desk',
      'linker HANDOFF visit',
      'signals WORKING desk',
      'signals HANDOFF visit',
      'sales WORKING desk',
      'support WORKING desk',
      'sales HANDOFF debate',
      'support HANDOFF debate',
      'reconciler WORKING desk',
      'reconciler HANDOFF visit',
      'brief-writer WORKING desk',
      'brief-writer HANDOFF visit',
    ]);
  });

  it('sends each hand-off to the next stage’s agents, carrying the result, with its arrow', () => {
    const handoffs = new Map<string, readonly string[]>();
    for (const { frame } of frames(timeline))
      for (const [agent, directive] of frame.directives)
        if (directive.state === 'HANDOFF' && directive.place.kind === 'visit') {
          handoffs.set(agent, directive.place.agentIds);
          expect(directive.carrying || frame.arrows.length > 0).toBe(true);
        }
    expect(Object.fromEntries(handoffs)).toEqual({
      memory: ['linker'],
      linker: ['signals'],
      signals: ['sales', 'support'],
      reconciler: ['brief-writer'],
      'brief-writer': ['ceo'],
    });
    const visit = placeSeat(layout, 'signals', { kind: 'visit', agentIds: ['sales', 'support'] });
    expect(visit.x).toBeCloseTo((2.4 + 5.6) / 2);
  });

  it('meets the analysts at the debate table under a red arrow, then the RECONCILER rules', () => {
    const conflict = frames(timeline).find(({ frame }) =>
      frame.arrows.some((arrow) => arrow.tone === 'conflict'),
    );
    expect(conflict?.frame.arrows).toEqual([
      expect.objectContaining({ tone: 'conflict', label: 'CONFLICT DEAL-001' }),
    ]);
    expect(conflict?.frame.directives.get('sales')?.place).toEqual({ kind: 'debate', seat: 0 });
    expect(conflict?.frame.directives.get('support')?.place).toEqual({ kind: 'debate', seat: 1 });
    const ruling = frames(timeline).find(
      ({ frame }) => frame.directives.get('reconciler')?.state === 'WORKING',
    );
    expect(ruling?.frame.directives.get('sales')).toMatchObject({
      state: 'DONE',
      place: { kind: 'debate' },
    });
    expect(debateSeat(9)).toBe(DEBATE_SEATS.at(-1));
  });

  it('fills the tray one sheet per inbox row, and leaves it to the inbox outside the show', () => {
    const counts = frames(timeline).map(({ frame }) => frame.trayCount);
    expect(counts[0]).toBe(0);
    expect([...new Set(counts)]).toEqual([0, 1, 2, 3, null]);
  });

  it('never makes anyone WORKING or HANDOFF but the episode’s agents', () => {
    const cast = new Set(participants(episode));
    for (const { frame } of frames(timeline))
      for (const [agent] of frame.directives) expect(cast.has(agent)).toBe(true);
  });

  it('lights a live run’s agents in stage order, captioned, for as long as it is in flight', () => {
    const live = liveTimeline(['memory', 'linker', 'signals'], 'ASSESSING…');
    expect(live.duration).toBe(Infinity);
    const early = frameAt(live, 0.1);
    expect(early.directives.get('memory')).toMatchObject({
      state: 'WORKING',
      caption: 'ASSESSING…',
    });
    expect(early.directives.get('linker')).toMatchObject({
      state: 'IDLE',
      place: { kind: 'desk' },
    });
    expect(frameAt(live, 3600).directives.get('signals')?.state).toBe('WORKING');
    expect(nextChange(live, 0)).toBeCloseTo(BEATS.liveStagger);
    expect(frameAt(live, 1).trayCount).toBeNull();
  });

  it('holds a finished run’s agents at their desks, idle, until the replay', () => {
    const hold = holdTimeline(['memory']);
    expect(frameAt(hold, 50).directives.get('memory')).toMatchObject({
      state: 'IDLE',
      place: { kind: 'desk' },
    });
    expect(nextChange(hold, 0)).toBe(Infinity);
  });

  it('never gathers for less than a moment', () => {
    const quick = replayTimeline(episode, layout, 0);
    expect(frameAt(quick, 0).directives.get('memory')?.arriveBy).toBe(BEATS.minimumGather);
  });

  it('plays an ingestion: the connector walks the outcome to MEMORY, which files it', () => {
    const run = loadExchanges('ingestion-run.json').find((exchange) => exchange.method === 'POST')
      ?.body as IngestionRunCreatedResponse;
    const ingestion = ingestionEpisode('csv_demo', run);
    const line = replayTimeline(ingestion, layout, 1);
    const all = frames(line);
    const carry = all.find(({ frame }) => frame.directives.get('csv_demo')?.state === 'HANDOFF');
    expect(carry?.frame.directives.get('csv_demo')).toMatchObject({
      place: { kind: 'visit', agentIds: ['memory'] },
      carrying: true,
    });
    expect(carry?.frame.arrows[0]).toMatchObject({
      tone: 'handoff',
      label: ingestion.steps[0]?.caption,
    });
    const filing = all.filter(({ frame }) => frame.directives.get('memory')?.state === 'WORKING');
    expect(filing.length).toBeGreaterThanOrEqual(run.entities.length > 0 ? 1 : 0);
    // The connector waits by MEMORY while it files, then both cheer.
    const end = frameAt(line, line.duration - 0.01);
    expect(end.directives.get('csv_demo')).toMatchObject({ cheer: true, place: { kind: 'visit' } });
  });

  it('walks the analysts to the BRIEF_WRITER when there is no conflict', () => {
    const cust025 = episodeFor('2026-09-18', list0918, 1);
    const line = replayTimeline(cust025, layout, 1);
    const handoff = frames(line).find(
      ({ frame }) => frame.directives.get('support')?.state === 'HANDOFF',
    );
    expect(handoff?.frame.directives.get('support')?.place).toEqual({
      kind: 'visit',
      agentIds: ['brief-writer'],
    });
  });

  it('lets the analysts go back to their desks when no ruling follows a conflict', () => {
    const conflictOnly: Episode = {
      kind: 'assessment',
      steps: [
        {
          stage: 5,
          kind: 'conflict',
          agents: ['sales', 'support'],
          to: null,
          caption: 'CONFLICT X',
          source: { route: 'r', path: 'p' },
          tray: null,
        },
        {
          stage: 5,
          kind: 'conflict',
          agents: ['sales'],
          to: null,
          caption: 'CONFLICT Y',
          source: { route: 'r', path: 'p' },
          tray: null,
        },
      ],
    };
    const line = replayTimeline(conflictOnly, layout, 1);
    // A conflict with one side only draws no arrow.
    expect(line.arrows.map((span) => span.arrow.label)).toEqual(['CONFLICT X']);
    const end = frameAt(line, line.duration - 0.01);
    expect(end.directives.get('sales')).toMatchObject({ cheer: true, place: { kind: 'desk' } });
  });

  it('plays a walk that takes no time as no cue at all', () => {
    const still = { ...layout, walkSeconds: () => 0 };
    const line = replayTimeline(episode, still, 1);
    for (const cues of line.cues.values())
      for (const cue of cues) expect(cue.end).toBeGreaterThan(cue.start);
  });

  it('places an agent the roster does not know at the origin', () => {
    expect(placeSeat(layout, 'x', { kind: 'visit', agentIds: ['nobody'] })).toMatchObject({
      x: 0,
      z: 1,
    });
    expect(placeSeat(layout, 'nobody', { kind: 'desk' })).toMatchObject({ x: 0, z: 0 });
    expect(placeSeat(layout, 'nobody', { kind: 'visit', agentIds: [] })).toMatchObject({
      x: 0,
      z: 0,
    });
  });
});

describe('walks (§9.7, §9.11)', () => {
  const mover = (): Mover => ({
    x: 0,
    z: 0,
    facing: 0,
    path: [
      [0, 0],
      [3, 0],
      [3, 4],
    ],
    next: 1,
  });

  it('walks along its path and arrives', () => {
    const walker = mover();
    expect(remaining(walker)).toBe(7);
    expect(advance(walker, 2, 1)).toBe(2);
    expect([walker.x, walker.z]).toEqual([2, 0]);
    expect(walker.facing).toBeCloseTo(Math.PI / 2);
    advance(walker, 4, 1);
    expect([walker.x, walker.z]).toEqual([3, 3]);
    expect(advance(walker, 10, 1)).toBe(1);
    expect(arrived(walker)).toBe(true);
    expect(advance(walker, 1, 1)).toBe(0);
  });

  it('turns at a bounded rate, the short way round', () => {
    expect(turnBetween(0, Math.PI / 2)).toBeCloseTo(Math.PI / 2);
    expect(turnBetween(0.1, 2 * Math.PI - 0.1)).toBeCloseTo(-0.2);
    expect(turnTowards(0, 1, 1)).toBe(1);
    expect(turnTowards(0, 3, 0.1)).toBeCloseTo(TURN_RATE * 0.1);
    expect(turnTowards(0, -3, 0.1)).toBeCloseTo(-TURN_RATE * 0.1);
    expect(headingOf(0, 1)).toBe(0);
  });

  it('keeps walking pace unless late, and hurries only so far', () => {
    expect(paceFor(10, null)).toBe(WALK_SPEED);
    expect(paceFor(10, 100)).toBe(WALK_SPEED);
    expect(paceFor(10, 2)).toBe(5);
    expect(paceFor(100, 1)).toBe(WALK_SPEED * HURRY);
    expect(paceFor(1, 0)).toBe(WALK_SPEED * HURRY);
  });

  it('stays put on a path to where it already is', () => {
    const walker: Mover = {
      x: 1,
      z: 1,
      facing: 2,
      path: [
        [1, 1],
        [1, 1],
      ],
      next: 1,
    };
    advance(walker, 1, 1);
    expect(walker.facing).toBe(2);
    expect(arrived(walker)).toBe(true);
  });
});

describe('the layout', () => {
  it('is built once per roster, and a gather covers the longest walk to a desk', () => {
    expect(officeLayout(roster)).toBe(layout);
    const walks = ['memory', 'brief-writer'].map((id) =>
      walkSeconds(grid, BREAK_MIDDLE, at(layout.seats.get(id)!)),
    );
    expect(gatherSeconds(layout, ['memory', 'brief-writer'])).toBeCloseTo(Math.max(...walks) + 1);
    expect(gatherSeconds(layout, ['nobody'])).toBe(1);
  });
});
