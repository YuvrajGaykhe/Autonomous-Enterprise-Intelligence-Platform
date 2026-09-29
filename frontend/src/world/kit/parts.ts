/**
 * The world's building blocks: every object in the office is a list of primitive parts, each a
 * shape, a finish, a colour and a transform. The world draws all parts of one shape and finish as
 * a single instanced mesh, which keeps the draw calls within budget (spec §9.10).
 */

import { Euler, Matrix4, Quaternion, Vector3 } from 'three';

export type Shape = 'box' | 'cylinder' | 'sphere' | 'cone' | 'torus';
/** `toon`: lit with the 3-step gradient; `glow`: unlit (screens, bulbs, lamps); `outline`: the working glow's hull. */
export type Finish = 'toon' | 'glow' | 'outline';

export interface Part {
  shape: Shape;
  finish: Finish;
  color: string;
  matrix: Matrix4;
}

export type Triple = readonly [number, number, number];

const position = new Vector3();
const scale = new Vector3();
const rotation = new Quaternion();
const euler = new Euler();

/**
 * A part of `size` centred at `at`. Sizes are in world units: a box's edges, a cylinder's or a
 * cone's diameter and height, a sphere's diameter, a torus's diameter (its tube is a fifth of it).
 */
export function part(
  shape: Shape,
  color: string,
  size: Triple,
  at: Triple,
  turn: Triple = [0, 0, 0],
  finish: Finish = 'toon',
): Part {
  euler.set(turn[0], turn[1], turn[2]);
  rotation.setFromEuler(euler);
  return {
    shape,
    finish,
    color,
    matrix: new Matrix4().compose(
      position.set(at[0], at[1], at[2]),
      rotation,
      scale.set(size[0], size[1], size[2]),
    ),
  };
}

export const box = (color: string, size: Triple, at: Triple, turn?: Triple) =>
  part('box', color, size, at, turn);
export const glowBox = (color: string, size: Triple, at: Triple, turn?: Triple) =>
  part('box', color, size, at, turn, 'glow');

/** `parts`, moved from their local frame to (`x`, `y`, `z`), turned `yaw` radians about +y. */
export function placed(parts: readonly Part[], x: number, y: number, z: number, yaw = 0): Part[] {
  const frame = new Matrix4().makeRotationY(yaw).setPosition(x, y, z);
  return parts.map((item) => ({ ...item, matrix: frame.clone().multiply(item.matrix) }));
}

/** A slightly larger copy of each part, drawn from behind in one colour: the glow hull (§9.3). */
export function outlined(parts: readonly Part[], color: string, grow = 1.14): Part[] {
  const scaleUp = new Matrix4().makeScale(grow, grow, grow);
  return parts.map((item) => ({
    ...item,
    finish: 'outline',
    color,
    matrix: item.matrix.clone().multiply(scaleUp),
  }));
}
