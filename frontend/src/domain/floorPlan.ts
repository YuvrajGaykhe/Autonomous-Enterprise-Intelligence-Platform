/**
 * The office floor plan (spec §9.1; the room set is DIRECTED, the grid, positions and furniture
 * are PROPOSED; plan §4.1).
 *
 * One world unit is about a metre. x runs west to east and z runs north to south, so the plan's
 * top row is the north row:
 *
 * ```
 *  z 0 ┌ Data Dock ──┬ Evidence Lab ┬ Signals Desk ┬ CEO Corner Office ┐
 *      │             │              │              │                   │
 *  z 8 ├ Analyst ────┼ Debate Table ┼ Brief Studio ┼ Break Area ───────┤
 *      │ Bullpen     │              │              │                   │
 * z 15 ├ Pipeline ───┼ Account 360 ─┼ War Room ────┼ Copilot Desk ─────┤  (locked)
 * z 20 └─────────────┴──────────────┴──────────────┴───────────────────┘
 *      x 0                                                            x 32
 * ```
 *
 * Every open room is reachable through doors; locked rooms have closed doors only (D-F-4).
 */

import { ROOMS, type Agent, type RoomId } from './roster';

export const FLOOR = { width: 32, depth: 20 } as const;

export interface Rect {
  x: number;
  z: number;
  width: number;
  depth: number;
}

export const ROOM_RECTS: Readonly<Record<RoomId, Rect>> = {
  'data-dock': { x: 0, z: 0, width: 10, depth: 8 },
  'evidence-lab': { x: 10, z: 0, width: 7, depth: 8 },
  'signals-desk': { x: 17, z: 0, width: 7, depth: 8 },
  'ceo-office': { x: 24, z: 0, width: 8, depth: 8 },
  'analyst-bullpen': { x: 0, z: 8, width: 8, depth: 7 },
  'debate-table': { x: 8, z: 8, width: 7, depth: 7 },
  'brief-studio': { x: 15, z: 8, width: 7, depth: 7 },
  'break-area': { x: 22, z: 8, width: 10, depth: 7 },
  'pipeline-room': { x: 0, z: 15, width: 8, depth: 5 },
  'account-360': { x: 8, z: 15, width: 8, depth: 5 },
  'war-room': { x: 16, z: 15, width: 8, depth: 5 },
  'copilot-desk': { x: 24, z: 15, width: 8, depth: 5 },
};

/**
 * Where each room's sign stands: open rooms just inside their north wall, clear of the furniture;
 * locked rooms in the middle of their floor.
 */
export const ROOM_LABEL_POINTS: Readonly<Record<RoomId, readonly [number, number]>> = {
  'data-dock': [4.4, 0.7],
  'evidence-lab': [14.6, 0.7],
  'signals-desk': [20.8, 0.7],
  'ceo-office': [28.4, 0.7],
  'analyst-bullpen': [1.9, 8.7],
  'debate-table': [11.5, 8.7],
  'brief-studio': [18.5, 8.7],
  'break-area': [27.6, 8.7],
  'pipeline-room': [4, 16.4],
  'account-360': [12, 16.2],
  'war-room': [20, 16.4],
  'copilot-desk': [28, 16.2],
};

export function rectCenter(rect: Rect): [number, number] {
  return [rect.x + rect.width / 2, rect.z + rect.depth / 2];
}

export function inRect(rect: Rect, x: number, z: number, margin = 0): boolean {
  return (
    x >= rect.x + margin &&
    x <= rect.x + rect.width - margin &&
    z >= rect.z + margin &&
    z <= rect.z + rect.depth - margin
  );
}

/** The room whose floor holds the point; a point on a shared wall belongs to the first listed. */
export function roomAt(x: number, z: number): RoomId | null {
  return ROOMS.find((room) => inRect(ROOM_RECTS[room.id], x, z))?.id ?? null;
}

export const WALL_THICKNESS = 0.2;
export const DOOR_WIDTH = 1.6;
/** Outer walls on the far side of the camera stand tall; every other wall is a low partition. */
export const WALL_HEIGHT = { tall: 2.4, low: 0.9 } as const;

export type Side = 'north' | 'west' | 'south' | 'east';

export interface WallLine {
  /** Along x when `axis` is `x` (at `at` = z), along z when `axis` is `z` (at `at` = x). */
  axis: 'x' | 'z';
  at: number;
  from: number;
  to: number;
  /** Door centres, along the wall. */
  doors: readonly number[];
  /** `outer` walls have a side; `locked` walls carry closed doors only. */
  kind: 'outer' | 'inner' | 'locked';
  side?: Side;
}

export const WALL_LINES: readonly WallLine[] = [
  { axis: 'x', at: 0, from: 0, to: 32, doors: [], kind: 'outer', side: 'north' },
  { axis: 'z', at: 0, from: 0, to: 20, doors: [], kind: 'outer', side: 'west' },
  { axis: 'x', at: 20, from: 0, to: 32, doors: [], kind: 'outer', side: 'south' },
  { axis: 'z', at: 32, from: 0, to: 20, doors: [], kind: 'outer', side: 'east' },
  // The north row to the middle row: one door per pair of rooms that meet.
  { axis: 'x', at: 8, from: 0, to: 32, doors: [4, 12.5, 19.5, 28], kind: 'inner' },
  // The middle row to the locked row: closed doors only.
  { axis: 'x', at: 15, from: 0, to: 32, doors: [4, 12, 20, 28], kind: 'locked' },
  { axis: 'z', at: 10, from: 0, to: 8, doors: [5], kind: 'inner' },
  { axis: 'z', at: 17, from: 0, to: 8, doors: [5], kind: 'inner' },
  { axis: 'z', at: 24, from: 0, to: 8, doors: [5], kind: 'inner' },
  { axis: 'z', at: 8, from: 8, to: 15, doors: [11.5], kind: 'inner' },
  { axis: 'z', at: 15, from: 8, to: 15, doors: [11.5], kind: 'inner' },
  { axis: 'z', at: 22, from: 8, to: 15, doors: [11.5], kind: 'inner' },
  { axis: 'z', at: 8, from: 15, to: 20, doors: [], kind: 'locked' },
  { axis: 'z', at: 16, from: 15, to: 20, doors: [], kind: 'locked' },
  { axis: 'z', at: 24, from: 15, to: 20, doors: [], kind: 'locked' },
];

/** The solid stretches of a wall: open doors are gaps, closed (locked) doors are not. */
export function wallSegments(line: WallLine): [number, number][] {
  if (line.kind !== 'inner') return [[line.from, line.to]];
  const segments: [number, number][] = [];
  let start = line.from;
  for (const door of [...line.doors].sort((a, b) => a - b)) {
    segments.push([start, door - DOOR_WIDTH / 2]);
    start = door + DOOR_WIDTH / 2;
  }
  segments.push([start, line.to]);
  return segments;
}

const OUTWARD: Readonly<Record<Side, [number, number]>> = {
  north: [0, -1],
  west: [-1, 0],
  south: [0, 1],
  east: [1, 0],
};

/**
 * Whether an outer wall is on the far side of the camera at `yaw` degrees (the camera stands on
 * +z at yaw 0, §9.8), so it may stand tall without hiding the floor.
 */
export function isFarWall(side: Side, yaw: number): boolean {
  const radians = (yaw * Math.PI) / 180;
  const [x, z] = OUTWARD[side];
  return x * Math.sin(radians) + z * Math.cos(radians) < -1e-9;
}

/** The rooms on either side of each door, open or closed, for the reachability checks. */
export function doorLinks(kind: 'inner' | 'locked'): [RoomId | null, RoomId | null][] {
  return WALL_LINES.filter((wall) => wall.kind === kind).flatMap((line) =>
    line.doors.map((door): [RoomId | null, RoomId | null] =>
      line.axis === 'x'
        ? [roomAt(door, line.at - 0.5), roomAt(door, line.at + 0.5)]
        : [roomAt(line.at - 0.5, door), roomAt(line.at + 0.5, door)],
    ),
  );
}

export type Pose = 'stand' | 'sit';

export interface Seat {
  x: number;
  z: number;
  /** The direction the agent faces, in radians about +y; 0 faces +z (south). */
  facing: number;
  pose: Pose;
}

/** The fixed agents' places. The CEO's is the empty chair: the user is the CEO (§9.9). */
const FIXED_SEATS: Readonly<Record<Exclude<Agent['kind'], 'connector'>, Seat>> = {
  memory: { x: 7.9, z: 2.6, facing: 0, pose: 'stand' },
  linker: { x: 13.5, z: 3.4, facing: 0, pose: 'sit' },
  signals: { x: 19.6, z: 3.4, facing: 0, pose: 'sit' },
  sales: { x: 2.4, z: 10.6, facing: 0, pose: 'sit' },
  support: { x: 5.6, z: 10.6, facing: 0, pose: 'sit' },
  reconciler: { x: 11.5, z: 10.5, facing: 0, pose: 'sit' },
  briefWriter: { x: 18.5, z: 10.6, facing: 0, pose: 'sit' },
  ceo: { x: 28, z: 3.3, facing: 0, pose: 'sit' },
};

/** Where connectors stand: a loading bay in the Data Dock's west half, three abreast. */
const BAY = { x: 1.3, z: 2.2, across: 1.8, lastZ: 6.8, perRow: 3, rowGap: 2 } as const;

export function connectorSeat(index: number, count: number): Seat {
  const rows = Math.max(1, Math.ceil(count / BAY.perRow));
  const gap = rows === 1 ? BAY.rowGap : Math.min(BAY.rowGap, (BAY.lastZ - BAY.z) / (rows - 1));
  return {
    x: BAY.x + (index % BAY.perRow) * BAY.across,
    z: BAY.z + Math.floor(index / BAY.perRow) * gap,
    facing: 0,
    pose: 'stand',
  };
}

/** Every agent's place, by agent id. */
export function seatsFor(roster: readonly Agent[]): Map<string, Seat> {
  const connectors = roster.filter((agent) => agent.kind === 'connector');
  return new Map(
    roster.map((agent) => [
      agent.id,
      agent.kind === 'connector'
        ? connectorSeat(connectors.indexOf(agent), connectors.length)
        : FIXED_SEATS[agent.kind],
    ]),
  );
}

export type FurnitureKind =
  | 'desk'
  | 'chair'
  | 'monitor'
  | 'serverRack'
  | 'crateStack'
  | 'pallet'
  | 'bookshelf'
  | 'filingCabinet'
  | 'plant'
  | 'roundTable'
  | 'sofa'
  | 'coffeeMachine'
  | 'waterCooler'
  | 'vendingMachine'
  | 'coffeeTable'
  | 'executiveDesk'
  | 'executiveChair'
  | 'corkboard'
  | 'rug'
  | 'signalsBoard'
  | 'typewriter'
  | 'abacus'
  | 'magnifierStand'
  | 'whiteboard'
  | 'coveredCrate'
  | 'lamp'
  | 'fridge'
  | 'arcadeCabinet'
  | 'pingPongTable'
  | 'armchair'
  | 'beanBag'
  | 'tvConsole'
  | 'loungeRug'
  | 'cafeTable'
  | 'cafeChair'
  | 'pizzaBox'
  | 'chargingPad';

export interface FurnitureItem {
  kind: FurnitureKind;
  x: number;
  z: number;
  /** Radians about +y. */
  rotation: number;
  room: RoomId;
}

const QUARTER = Math.PI / 2;

/** A desk in front of a seat, its chair and monitor, and one role prop on the desk. */
function deskFor(room: RoomId, seat: Seat, prop?: FurnitureKind): FurnitureItem[] {
  return [
    { kind: 'chair', x: seat.x, z: seat.z - 0.05, rotation: 0, room },
    { kind: 'desk', x: seat.x, z: seat.z + 0.75, rotation: 0, room },
    { kind: 'monitor', x: seat.x - 0.15, z: seat.z + 0.95, rotation: Math.PI, room },
    ...(prop === undefined
      ? []
      : [{ kind: prop, x: seat.x + 0.5, z: seat.z + 0.7, rotation: 0, room }]),
  ];
}

/** The fixed furniture of the open and locked rooms. Connector props follow the connectors. */
export const FURNITURE: readonly FurnitureItem[] = [
  // Data Dock: MEMORY's archive of server racks along the north wall, pallets and a shelf.
  { kind: 'serverRack', x: 6.6, z: 0.7, rotation: 0, room: 'data-dock' },
  { kind: 'serverRack', x: 7.9, z: 0.7, rotation: 0, room: 'data-dock' },
  { kind: 'serverRack', x: 9.2, z: 0.7, rotation: 0, room: 'data-dock' },
  { kind: 'pallet', x: 8.4, z: 6.4, rotation: 0, room: 'data-dock' },
  { kind: 'plant', x: 0.6, z: 7.3, rotation: 0, room: 'data-dock' },
  // Evidence Lab.
  ...deskFor('evidence-lab', FIXED_SEATS.linker, 'magnifierStand'),
  { kind: 'bookshelf', x: 11.2, z: 0.5, rotation: 0, room: 'evidence-lab' },
  { kind: 'bookshelf', x: 12.6, z: 0.5, rotation: 0, room: 'evidence-lab' },
  { kind: 'filingCabinet', x: 16.3, z: 1.2, rotation: -QUARTER, room: 'evidence-lab' },
  { kind: 'filingCabinet', x: 16.3, z: 2.1, rotation: -QUARTER, room: 'evidence-lab' },
  { kind: 'plant', x: 10.6, z: 7.3, rotation: 0, room: 'evidence-lab' },
  // Signals Desk: the board that shows the real signals (§9.2).
  ...deskFor('signals-desk', FIXED_SEATS.signals, 'abacus'),
  { kind: 'signalsBoard', x: 22.3, z: 3.2, rotation: 0, room: 'signals-desk' },
  { kind: 'lamp', x: 17.6, z: 0.6, rotation: 0, room: 'signals-desk' },
  { kind: 'plant', x: 23.4, z: 7.3, rotation: 0, room: 'signals-desk' },
  // CEO Corner Office: the executive desk with its empty chair, the corkboard, a rug.
  { kind: 'rug', x: 28, z: 4.4, rotation: 0, room: 'ceo-office' },
  { kind: 'executiveChair', x: 28, z: 3.25, rotation: 0, room: 'ceo-office' },
  { kind: 'executiveDesk', x: 28, z: 4.3, rotation: 0, room: 'ceo-office' },
  { kind: 'corkboard', x: 30.9, z: 2.2, rotation: -QUARTER, room: 'ceo-office' },
  { kind: 'bookshelf', x: 25.2, z: 0.5, rotation: 0, room: 'ceo-office' },
  { kind: 'plant', x: 31.4, z: 0.6, rotation: 0, room: 'ceo-office' },
  { kind: 'plant', x: 24.6, z: 7.3, rotation: 0, room: 'ceo-office' },
  // Analyst Bullpen.
  ...deskFor('analyst-bullpen', FIXED_SEATS.sales),
  ...deskFor('analyst-bullpen', FIXED_SEATS.support),
  { kind: 'whiteboard', x: 4, z: 8.5, rotation: 0, room: 'analyst-bullpen' },
  { kind: 'plant', x: 0.6, z: 14.3, rotation: 0, room: 'analyst-bullpen' },
  // Debate Table: the round table and its chairs.
  { kind: 'roundTable', x: 11.5, z: 11.8, rotation: 0, room: 'debate-table' },
  { kind: 'chair', x: 11.5, z: 10.45, rotation: 0, room: 'debate-table' },
  { kind: 'chair', x: 10.1, z: 12.3, rotation: QUARTER, room: 'debate-table' },
  { kind: 'chair', x: 12.9, z: 12.3, rotation: -QUARTER, room: 'debate-table' },
  { kind: 'plant', x: 14.4, z: 14.3, rotation: 0, room: 'debate-table' },
  // Brief Studio.
  ...deskFor('brief-studio', FIXED_SEATS.briefWriter, 'typewriter'),
  { kind: 'filingCabinet', x: 21.3, z: 9, rotation: -QUARTER, room: 'brief-studio' },
  { kind: 'lamp', x: 15.6, z: 14.3, rotation: 0, room: 'brief-studio' },
  // Break Area: where every agent not at work spends its time (§9.7; the owner's F4 ruling). A
  // kitchenette along the north wall, games in the middle, a lounge facing the TV in the west and
  // a café corner in the east. `breakArea.ts` lists the places an agent can take here.
  { kind: 'coffeeMachine', x: 23, z: 8.7, rotation: 0, room: 'break-area' },
  { kind: 'waterCooler', x: 24.35, z: 8.6, rotation: 0, room: 'break-area' },
  { kind: 'fridge', x: 25.3, z: 8.55, rotation: 0, room: 'break-area' },
  { kind: 'plant', x: 26.55, z: 8.5, rotation: 0, room: 'break-area' },
  { kind: 'arcadeCabinet', x: 29.6, z: 8.55, rotation: 0, room: 'break-area' },
  { kind: 'vendingMachine', x: 31.3, z: 9.4, rotation: -QUARTER, room: 'break-area' },
  { kind: 'chargingPad', x: 26.9, z: 10, rotation: 0, room: 'break-area' },
  { kind: 'pingPongTable', x: 29, z: 11.4, rotation: 0, room: 'break-area' },
  { kind: 'loungeRug', x: 24.6, z: 13.3, rotation: 0, room: 'break-area' },
  { kind: 'tvConsole', x: 22.45, z: 13.3, rotation: QUARTER, room: 'break-area' },
  { kind: 'coffeeTable', x: 24.2, z: 13.3, rotation: QUARTER, room: 'break-area' },
  { kind: 'pizzaBox', x: 24.2, z: 13.55, rotation: 0.3, room: 'break-area' },
  { kind: 'sofa', x: 25.9, z: 13.3, rotation: -QUARTER, room: 'break-area' },
  { kind: 'armchair', x: 24.2, z: 14.45, rotation: Math.PI, room: 'break-area' },
  { kind: 'beanBag', x: 23.1, z: 14.5, rotation: Math.PI, room: 'break-area' },
  { kind: 'lamp', x: 26.75, z: 14.65, rotation: 0, room: 'break-area' },
  { kind: 'beanBag', x: 27.7, z: 14.35, rotation: Math.PI, room: 'break-area' },
  { kind: 'beanBag', x: 28.75, z: 14.4, rotation: Math.PI, room: 'break-area' },
  { kind: 'cafeTable', x: 30.3, z: 13.7, rotation: 0, room: 'break-area' },
  { kind: 'cafeChair', x: 29.55, z: 13.7, rotation: QUARTER, room: 'break-area' },
  { kind: 'cafeChair', x: 31.05, z: 13.7, rotation: -QUARTER, room: 'break-area' },
  { kind: 'plant', x: 31.45, z: 14.5, rotation: 0, room: 'break-area' },
  // Locked rooms: covered crates, waiting for their slice (D-F-4).
  { kind: 'coveredCrate', x: 3, z: 17.5, rotation: 0, room: 'pipeline-room' },
  { kind: 'coveredCrate', x: 5.4, z: 18, rotation: 0.4, room: 'pipeline-room' },
  { kind: 'coveredCrate', x: 11, z: 17.8, rotation: 0, room: 'account-360' },
  { kind: 'coveredCrate', x: 13.3, z: 17.2, rotation: -0.3, room: 'account-360' },
  { kind: 'coveredCrate', x: 19.2, z: 17.6, rotation: 0.2, room: 'war-room' },
  { kind: 'coveredCrate', x: 21.6, z: 18.1, rotation: 0, room: 'war-room' },
  { kind: 'coveredCrate', x: 27, z: 17.4, rotation: 0, room: 'copilot-desk' },
  { kind: 'coveredCrate', x: 29.5, z: 18, rotation: -0.5, room: 'copilot-desk' },
];

/** The props that follow each connector: a crate stack beside it. */
export function connectorProps(seat: Seat): FurnitureItem[] {
  return [
    { kind: 'crateStack', x: seat.x + 0.75, z: seat.z + 0.1, rotation: 0, room: 'data-dock' },
  ];
}

/** All the furniture of an office with this roster: the fixed pieces and each connector's crates. */
export function officeFurniture(roster: readonly Agent[]): FurnitureItem[] {
  const seats = seatsFor(roster);
  return [
    ...FURNITURE,
    ...roster.flatMap((agent) => {
      const seat = agent.kind === 'connector' ? seats.get(agent.id) : undefined;
      return seat === undefined ? [] : connectorProps(seat);
    }),
  ];
}

/**
 * Where an agent stands to hand something to `receiver` (the owner's F4 ruling: a hand-off walks
 * to the receiver): across the desk of a seated agent, beside the RECONCILER at the debate table,
 * in front of one who stands, and at the tray of the CEO's desk.
 */
export function visitPoint(receiver: Agent['kind'], seat: Seat): Seat {
  switch (receiver) {
    case 'ceo':
      return { x: seat.x + 0.6, z: seat.z + 2.05, facing: Math.PI, pose: 'stand' };
    case 'reconciler':
      return { x: seat.x + 1, z: seat.z - 0.1, facing: -QUARTER, pose: 'stand' };
    case 'memory':
      return { x: seat.x, z: seat.z + 1.1, facing: Math.PI, pose: 'stand' };
    case 'connector':
      return { x: seat.x, z: seat.z + 1, facing: Math.PI, pose: 'stand' };
    default:
      return { x: seat.x, z: seat.z + 1.5, facing: Math.PI, pose: 'stand' };
  }
}

/**
 * The places at the debate table for the agents of a conflict (§9.5 step 5): the two side chairs,
 * then standing room at the far side for any more.
 */
export const DEBATE_SEATS: readonly Seat[] = [
  { x: 10.1, z: 12.3, facing: QUARTER, pose: 'sit' },
  { x: 12.9, z: 12.3, facing: -QUARTER, pose: 'sit' },
  { x: 11.5, z: 13.35, facing: Math.PI, pose: 'stand' },
];

export function debateSeat(index: number): Seat {
  return DEBATE_SEATS[Math.min(index, DEBATE_SEATS.length - 1)] as Seat;
}
