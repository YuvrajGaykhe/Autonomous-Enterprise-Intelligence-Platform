/**
 * How a body moves its limbs (spec §9.9: stand, walk, sit, type, present, cheer; the owner's F4
 * ruling). Each animation gives the legs and arms an angle about their hip or shoulder, in radians
 * about x (negative swings forward and up), and a small bob of the whole body.
 *
 * Without animation (reduced motion, §9.11, or `still`) a pose keeps its shape but nothing swings.
 */

import { Matrix4 } from 'three';

import type { Rig, Segment } from './characters';

export type Animation =
  'idle' | 'walk' | 'type' | 'work' | 'present' | 'play' | 'sip' | 'cheer' | 'carry' | 'carryWalk';

export interface Limbs {
  bob: number;
  legLeft: number;
  legRight: number;
  armLeft: number;
  armRight: number;
}

const REST: Limbs = { bob: 0, legLeft: 0, legRight: 0, armLeft: 0, armRight: 0 };

/**
 * The limbs at `time` seconds; `phase` is the walk cycle's angle. With `animate` false, the pose's
 * shape without its swing.
 */
export function limbs(animation: Animation, phase: number, time: number, animate: boolean): Limbs {
  const wave = (rate: number) => (animate ? Math.sin(time * rate) : 0);
  const stride = animate ? Math.sin(phase) : 0;
  switch (animation) {
    case 'idle':
      return { ...REST, bob: wave(2) * 0.012 };
    case 'walk':
      return {
        bob: animate ? Math.abs(Math.cos(phase)) * 0.05 : 0,
        legLeft: stride * 0.55,
        legRight: -stride * 0.55,
        armLeft: -stride * 0.45,
        armRight: stride * 0.45,
      };
    case 'carry':
      return { ...REST, armLeft: -1, armRight: -1 };
    case 'carryWalk':
      return {
        bob: animate ? Math.abs(Math.cos(phase)) * 0.04 : 0,
        legLeft: stride * 0.55,
        legRight: -stride * 0.55,
        armLeft: -1,
        armRight: -1,
      };
    case 'type':
      return { ...REST, armLeft: wave(18) * 0.12, armRight: -wave(18) * 0.12 };
    case 'work':
      return { ...REST, armLeft: -0.9 + wave(6) * 0.25, armRight: -0.9 - wave(6) * 0.25 };
    case 'present':
      return { ...REST, armRight: -1.5 + wave(3) * 0.08 };
    case 'play':
      return { ...REST, bob: wave(7) * 0.02, armLeft: -0.4, armRight: -1.1 + wave(7) * 0.5 };
    case 'sip': {
      // Every four seconds the cup comes up for a sip.
      const cycle = animate ? time % 4 : 0;
      const lift = cycle > 2.4 && cycle < 3.6 ? Math.sin(((cycle - 2.4) / 1.2) * Math.PI) : 0;
      return { ...REST, armRight: -0.5 - lift * 1.7 };
    }
    case 'cheer':
      return {
        bob: animate ? Math.abs(Math.sin(time * 8)) * 0.14 : 0,
        legLeft: 0,
        legRight: 0,
        armLeft: -2.9 + wave(10) * 0.15,
        armRight: -2.9 - wave(10) * 0.15,
      };
  }
}

/** A turn of `angle` about x through the point (0, `height`, 0), written into `target`. */
function turnAbout(target: Matrix4, height: number, angle: number): Matrix4 {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  // prettier-ignore
  return target.set(
    1, 0, 0, 0,
    0, cos, -sin, height * (1 - cos),
    0, sin, cos, -height * sin,
    0, 0, 0, 1,
  );
}

export function segmentSet(): Record<Segment, Matrix4> {
  return {
    body: new Matrix4(),
    legLeft: new Matrix4(),
    legRight: new Matrix4(),
    armLeft: new Matrix4(),
    armRight: new Matrix4(),
  };
}

/**
 * Each segment's transform in the body's frame, written into `out`: a turn about the hip or the
 * shoulder. A seated body's legs are bent under the desk and stay put.
 */
export function segmentMatrices(
  rig: Rig,
  pose: Limbs,
  out: Record<Segment, Matrix4> = segmentSet(),
): Record<Segment, Matrix4> {
  const legsSwing = rig.pose === 'stand';
  out.body.identity();
  turnAbout(out.legLeft, rig.hip, legsSwing ? pose.legLeft : 0);
  turnAbout(out.legRight, rig.hip, legsSwing ? pose.legRight : 0);
  turnAbout(out.armLeft, rig.shoulder, pose.armLeft);
  turnAbout(out.armRight, rig.shoulder, pose.armRight);
  return out;
}
