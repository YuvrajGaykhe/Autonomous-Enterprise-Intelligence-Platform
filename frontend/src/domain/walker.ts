/**
 * One agent's walk along its path (the owner's F4 ruling; spec §9.7, §9.11): where it is, which
 * way it faces, and how fast it goes. The world moves every body with these each frame.
 *
 * An agent walks at walking pace, and hurries (up to a limit) when the Director needs it somewhere
 * by a given moment. It turns towards where it is going at a bounded rate, and on arrival turns to
 * face the way its place faces. Under reduced motion there is no walk: it is simply placed.
 */

import { WALK_SPEED, type Point } from './walkGrid';

/** The most an agent hurries: this many times walking pace (PROPOSED). */
export const HURRY = 1.8;
/** How fast a body turns, in radians per second (PROPOSED). */
export const TURN_RATE = 9;

export interface Mover {
  x: number;
  z: number;
  /** Radians about +y; 0 faces +z. */
  facing: number;
  path: readonly Point[];
  /** The index of the waypoint it is heading for; `path.length` once it has arrived. */
  next: number;
}

export function arrived(mover: Mover): boolean {
  return mover.next >= mover.path.length;
}

/** How far is left to walk. */
export function remaining(mover: Mover): number {
  let left = 0;
  let from: Point = [mover.x, mover.z];
  for (let index = mover.next; index < mover.path.length; index += 1) {
    const point = mover.path[index] as Point;
    left += Math.hypot(point[0] - from[0], point[1] - from[1]);
    from = point;
  }
  return left;
}

/** Walking pace, or faster when `secondsLeft` would not otherwise be enough. */
export function paceFor(distance: number, secondsLeft: number | null): number {
  if (secondsLeft === null) return WALK_SPEED;
  if (secondsLeft <= 0) return WALK_SPEED * HURRY;
  return Math.min(WALK_SPEED * HURRY, Math.max(WALK_SPEED, distance / secondsLeft));
}

/** The shortest signed turn from `from` to `to`, in (-π, π]. */
export function turnBetween(from: number, to: number): number {
  const turn = (((to - from) % (2 * Math.PI)) + 3 * Math.PI) % (2 * Math.PI);
  return turn - Math.PI;
}

/** `facing` turned towards `goal` by at most `rate × seconds`. */
export function turnTowards(facing: number, goal: number, seconds: number): number {
  const turn = turnBetween(facing, goal);
  const most = TURN_RATE * seconds;
  return Math.abs(turn) <= most ? goal : facing + Math.sign(turn) * most;
}

/** The heading of a step from (x, z) by (dx, dz), as a facing. */
export function headingOf(dx: number, dz: number): number {
  return Math.atan2(dx, dz);
}

/** Walk `distance` along the path, turning towards the way it goes. Returns the distance walked. */
export function advance(mover: Mover, distance: number, seconds: number): number {
  let left = distance;
  while (left > 0 && !arrived(mover)) {
    const target = mover.path[mover.next] as Point;
    const dx = target[0] - mover.x;
    const dz = target[1] - mover.z;
    const gap = Math.hypot(dx, dz);
    if (gap > 1e-6) mover.facing = turnTowards(mover.facing, headingOf(dx, dz), seconds);
    if (gap <= left) {
      mover.x = target[0];
      mover.z = target[1];
      mover.next += 1;
      left -= gap;
    } else {
      mover.x += (dx / gap) * left;
      mover.z += (dz / gap) * left;
      left = 0;
    }
  }
  return distance - left;
}
