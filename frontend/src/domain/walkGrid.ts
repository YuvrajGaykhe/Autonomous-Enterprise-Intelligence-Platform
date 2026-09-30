/**
 * The walk grid and its path finder (spec §9.7, §14 F4; the owner's F4 ruling that agents walk).
 *
 * The floor is cut into square cells. A cell is blocked by a wall (open doors are gaps) or by a
 * piece of furniture, each grown by an agent's reach so bodies keep clear of edges. Paths are A*
 * over the eight neighbours of a cell, never cutting a blocked corner, then pulled tight: a
 * waypoint is kept only where a straight line would cross a blocked cell.
 *
 * Written for this project rather than vendored from Claw3D (plan §5 named its module): fetching
 * that code is an outward action, and a grid A* is small. So nothing here needs a notice.
 */

import {
  FLOOR,
  WALL_LINES,
  WALL_THICKNESS,
  wallSegments,
  type FurnitureItem,
  type FurnitureKind,
} from './floorPlan';

/** The side of one cell, in world units. */
export const CELL = 0.25;
/** How far an agent's body reaches from its centre: walls and furniture grow by this much. */
export const REACH = 0.18;
/** How fast an agent walks, in world units per second (PROPOSED). */
export const WALK_SPEED = 4;

export type Point = readonly [number, number];

/** Width (local x) and depth (local z) each kind blocks; null for what agents walk over or sit on. */
export const FOOTPRINTS: Readonly<Record<FurnitureKind, readonly [number, number] | null>> = {
  desk: [1.3, 0.62],
  chair: [0.46, 0.44],
  monitor: null,
  serverRack: [1.1, 0.7],
  crateStack: [0.52, 0.52],
  pallet: [1.2, 0.95],
  bookshelf: [1.25, 0.4],
  filingCabinet: [0.55, 0.6],
  plant: [0.45, 0.45],
  roundTable: [1.9, 1.9],
  sofa: [2.1, 0.85],
  coffeeMachine: [1.24, 0.6],
  waterCooler: [0.4, 0.4],
  vendingMachine: [0.95, 0.7],
  coffeeTable: [1.1, 0.6],
  executiveDesk: [2.1, 0.95],
  executiveChair: [0.62, 0.58],
  corkboard: [1.5, 0.12],
  rug: null,
  // The board turns to face the camera, so it blocks the circle its legs sweep.
  signalsBoard: [2, 2],
  typewriter: null,
  abacus: null,
  magnifierStand: null,
  whiteboard: [1.7, 0.12],
  coveredCrate: [1.08, 0.88],
  lamp: [0.3, 0.3],
  fridge: [0.7, 0.66],
  arcadeCabinet: [0.8, 0.72],
  pingPongTable: [2, 1.1],
  armchair: [0.72, 0.7],
  beanBag: [0.8, 0.8],
  tvConsole: [1.6, 0.46],
  loungeRug: null,
  cafeTable: [0.7, 0.7],
  cafeChair: [0.42, 0.42],
  pizzaBox: null,
  chargingPad: null,
};

/** What a cell holds. */
export const FREE = 0;
export const FURNITURE_CELL = 1;
export const WALL_CELL = 2;

/** The four sides of a cell, then its four corners. */
const STEPS: readonly (readonly [number, number])[] = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
  [1, 1],
  [1, -1],
  [-1, 1],
  [-1, -1],
];

export interface WalkGrid {
  columns: number;
  rows: number;
  /** One byte per cell, row by row: free, furniture or wall. */
  cells: Uint8Array;
  /**
   * 1 for a free cell joined to the open floor (the largest free region), else 0. Pockets of free
   * cells shut in by furniture, and the locked rooms, are not.
   */
  open: Uint8Array;
}

function blockRect(
  grid: WalkGrid,
  x0: number,
  z0: number,
  x1: number,
  z1: number,
  kind: number,
): void {
  const c0 = Math.max(0, Math.floor(x0 / CELL));
  const c1 = Math.min(grid.columns - 1, Math.ceil(x1 / CELL) - 1);
  const r0 = Math.max(0, Math.floor(z0 / CELL));
  const r1 = Math.min(grid.rows - 1, Math.ceil(z1 / CELL) - 1);
  for (let row = r0; row <= r1; row += 1)
    for (let column = c0; column <= c1; column += 1) {
      const index = row * grid.columns + column;
      grid.cells[index] = Math.max(grid.cells[index] as number, kind);
    }
}

/** The axis-aligned box an item covers, turned by its rotation. */
export function footprintBox(item: FurnitureItem): [number, number, number, number] | null {
  const size = FOOTPRINTS[item.kind];
  if (size === null) return null;
  const [width, depth] = size;
  const cos = Math.abs(Math.cos(item.rotation));
  const sin = Math.abs(Math.sin(item.rotation));
  const halfX = (width * cos + depth * sin) / 2;
  const halfZ = (width * sin + depth * cos) / 2;
  return [item.x - halfX, item.z - halfZ, item.x + halfX, item.z + halfZ];
}

/** The grid of a floor with these walls and this furniture. */
export function buildWalkGrid(furniture: readonly FurnitureItem[]): WalkGrid {
  const columns = Math.round(FLOOR.width / CELL);
  const rows = Math.round(FLOOR.depth / CELL);
  const grid: WalkGrid = {
    columns,
    rows,
    cells: new Uint8Array(columns * rows),
    open: new Uint8Array(columns * rows),
  };
  const half = WALL_THICKNESS / 2 + REACH;
  for (const line of WALL_LINES) {
    for (const [from, to] of wallSegments(line)) {
      if (line.axis === 'x') blockRect(grid, from, line.at - half, to, line.at + half, WALL_CELL);
      else blockRect(grid, line.at - half, from, line.at + half, to, WALL_CELL);
    }
  }
  for (const item of furniture) {
    const box = footprintBox(item);
    if (box === null) continue;
    blockRect(grid, box[0] - REACH, box[1] - REACH, box[2] + REACH, box[3] + REACH, FURNITURE_CELL);
  }
  markOpenFloor(grid);
  return grid;
}

/** Flood the free regions and mark the largest as the open floor. */
export function markOpenFloor(grid: WalkGrid): void {
  const region = new Int32Array(grid.cells.length).fill(-1);
  let largest = -1;
  let largestSize = 0;
  let regions = 0;
  for (let seed = 0; seed < grid.cells.length; seed += 1) {
    if (grid.cells[seed] !== FREE || region[seed] !== -1) continue;
    const id = regions;
    regions += 1;
    region[seed] = id;
    const stack = [seed];
    let size = 0;
    while (stack.length > 0) {
      const cell = stack.pop() as number;
      size += 1;
      const column = cell % grid.columns;
      const row = Math.floor(cell / grid.columns);
      for (const [dc, dr] of STEPS.slice(0, 4)) {
        const c = column + dc;
        const r = row + dr;
        if (c < 0 || r < 0 || c >= grid.columns || r >= grid.rows) continue;
        const neighbour = r * grid.columns + c;
        if (grid.cells[neighbour] !== FREE || region[neighbour] !== -1) continue;
        region[neighbour] = id;
        stack.push(neighbour);
      }
    }
    if (size > largestSize) {
      largest = id;
      largestSize = size;
    }
  }
  for (let cell = 0; cell < grid.cells.length; cell += 1)
    grid.open[cell] = region[cell] === largest ? 1 : 0;
}

function cellOf(grid: WalkGrid, point: Point): number {
  const column = Math.min(grid.columns - 1, Math.max(0, Math.floor(point[0] / CELL)));
  const row = Math.min(grid.rows - 1, Math.max(0, Math.floor(point[1] / CELL)));
  return row * grid.columns + column;
}

export function centreOf(grid: WalkGrid, cell: number): Point {
  return [((cell % grid.columns) + 0.5) * CELL, (Math.floor(cell / grid.columns) + 0.5) * CELL];
}

/** Whether `point` lies on the open floor. */
export function isFree(grid: WalkGrid, point: Point): boolean {
  return grid.open[cellOf(grid, point)] === 1;
}

/**
 * The open-floor cell nearest `point`, searching outwards through furniture but never through a
 * wall, so an agent seated at a desk leaves by the side of the desk it sits on. Null inside a
 * locked room.
 */
export function nearestFreeCell(grid: WalkGrid, point: Point): number | null {
  const start = cellOf(grid, point);
  if (grid.open[start] === 1) return start;
  const seen = new Set([start]);
  let frontier = [start];
  while (frontier.length > 0) {
    const next: number[] = [];
    for (const cell of frontier) {
      const column = cell % grid.columns;
      const row = Math.floor(cell / grid.columns);
      for (const [dc, dr] of STEPS.slice(0, 4)) {
        const c = column + dc;
        const r = row + dr;
        if (c < 0 || r < 0 || c >= grid.columns || r >= grid.rows) continue;
        const neighbour = r * grid.columns + c;
        if (seen.has(neighbour)) continue;
        seen.add(neighbour);
        if (grid.open[neighbour] === 1) return neighbour;
        // Out through furniture and shut-in pockets, never through a wall.
        if (grid.cells[neighbour] !== WALL_CELL) next.push(neighbour);
      }
    }
    frontier = next;
  }
  return null;
}

/** A binary min-heap of cells keyed by their estimated cost. */
class Heap {
  private readonly cells: number[] = [];
  private readonly keys: number[] = [];

  get size(): number {
    return this.cells.length;
  }

  push(cell: number, key: number): void {
    this.cells.push(cell);
    this.keys.push(key);
    let index = this.cells.length - 1;
    while (index > 0) {
      const parent = (index - 1) >> 1;
      if ((this.keys[parent] as number) <= key) break;
      this.swap(index, parent);
      index = parent;
    }
  }

  pop(): number {
    const top = this.cells[0] as number;
    const lastCell = this.cells.pop() as number;
    const lastKey = this.keys.pop() as number;
    if (this.cells.length > 0) {
      this.cells[0] = lastCell;
      this.keys[0] = lastKey;
      let index = 0;
      for (;;) {
        const left = index * 2 + 1;
        const right = left + 1;
        let smallest = index;
        if (
          left < this.cells.length &&
          (this.keys[left] as number) < (this.keys[smallest] as number)
        )
          smallest = left;
        if (
          right < this.cells.length &&
          (this.keys[right] as number) < (this.keys[smallest] as number)
        )
          smallest = right;
        if (smallest === index) break;
        this.swap(index, smallest);
        index = smallest;
      }
    }
    return top;
  }

  private swap(a: number, b: number): void {
    [this.cells[a], this.cells[b]] = [this.cells[b] as number, this.cells[a] as number];
    [this.keys[a], this.keys[b]] = [this.keys[b] as number, this.keys[a] as number];
  }
}

function octile(grid: WalkGrid, a: number, b: number): number {
  const dx = Math.abs((a % grid.columns) - (b % grid.columns));
  const dz = Math.abs(Math.floor(a / grid.columns) - Math.floor(b / grid.columns));
  return Math.max(dx, dz) + (Math.SQRT2 - 1) * Math.min(dx, dz);
}

/** A* between two free cells: the cells of a shortest path, both ends included, or null. */
function search(grid: WalkGrid, from: number, to: number): number[] | null {
  const cost = new Float64Array(grid.cells.length).fill(Infinity);
  const came = new Int32Array(grid.cells.length).fill(-1);
  const closed = new Uint8Array(grid.cells.length);
  const open = new Heap();
  cost[from] = 0;
  open.push(from, octile(grid, from, to));
  while (open.size > 0) {
    const cell = open.pop();
    if (cell === to) {
      const path = [cell];
      let at = cell;
      while (at !== from) {
        at = came[at] as number;
        path.push(at);
      }
      return path.reverse();
    }
    if (closed[cell] === 1) continue;
    closed[cell] = 1;
    const column = cell % grid.columns;
    const row = Math.floor(cell / grid.columns);
    for (const [dc, dr] of STEPS) {
      const c = column + dc;
      const r = row + dr;
      if (c < 0 || r < 0 || c >= grid.columns || r >= grid.rows) continue;
      const neighbour = r * grid.columns + c;
      if (grid.cells[neighbour] !== FREE || closed[neighbour] === 1) continue;
      const diagonal = dc !== 0 && dr !== 0;
      if (
        diagonal &&
        (grid.cells[row * grid.columns + c] !== FREE ||
          grid.cells[r * grid.columns + column] !== FREE)
      )
        continue;
      const next = (cost[cell] as number) + (diagonal ? Math.SQRT2 : 1);
      if (next >= (cost[neighbour] as number)) continue;
      cost[neighbour] = next;
      came[neighbour] = cell;
      open.push(neighbour, next + octile(grid, neighbour, to));
    }
  }
  return null;
}

/** Whether a straight walk from `a` to `b` stays on free cells. */
export function clearLine(grid: WalkGrid, a: Point, b: Point): boolean {
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const steps = Math.max(1, Math.ceil(length / (CELL / 3)));
  for (let step = 0; step <= steps; step += 1) {
    const t = step / steps;
    if (!isFree(grid, [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])) return false;
  }
  return true;
}

/** Keep a waypoint only where the line from the last kept one would leave the free cells. */
function pull(grid: WalkGrid, points: readonly Point[]): Point[] {
  if (points.length <= 2) return [...points];
  const kept: Point[] = [points[0] as Point];
  let anchor = 0;
  while (anchor < points.length - 1) {
    let reach = anchor + 1;
    for (let candidate = anchor + 2; candidate < points.length; candidate += 1) {
      if (!clearLine(grid, points[anchor] as Point, points[candidate] as Point)) break;
      reach = candidate;
    }
    kept.push(points[reach] as Point);
    anchor = reach;
  }
  return kept;
}

/**
 * The waypoints of a walk from `from` to `to`, both included. Either end may lie on furniture (a
 * chair, a sofa): the walk leaves it for, and arrives from, the nearest free cell. Null when no
 * walk exists, for example into a locked room.
 */
export function findPath(grid: WalkGrid, from: Point, to: Point): Point[] | null {
  if (Math.hypot(to[0] - from[0], to[1] - from[1]) < 1e-6) return [from, to];
  const start = nearestFreeCell(grid, from);
  const goal = nearestFreeCell(grid, to);
  if (start === null || goal === null) return null;
  const cells = search(grid, start, goal);
  if (cells === null) return null;
  // A free end stands in for its own cell's centre; an end on furniture keeps the step to it.
  const middle = cells
    .map((cell) => centreOf(grid, cell))
    .slice(isFree(grid, from) ? 1 : 0, isFree(grid, to) ? -1 : undefined);
  return pull(grid, [from, ...middle, to]);
}

export function pathLength(points: readonly Point[]): number {
  let length = 0;
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1] as Point;
    const b = points[index] as Point;
    length += Math.hypot(b[0] - a[0], b[1] - a[1]);
  }
  return length;
}

/** How long a walk takes at walking pace, in seconds; a walk that cannot be made takes none. */
export function walkSeconds(grid: WalkGrid, from: Point, to: Point): number {
  const path = findPath(grid, from, to);
  return path === null ? 0 : pathLength(path) / WALK_SPEED;
}
