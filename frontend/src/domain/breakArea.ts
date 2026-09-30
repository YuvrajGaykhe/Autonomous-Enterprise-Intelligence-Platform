/**
 * The Break Area's places (spec §9.7; the owner's F4 ruling: an agent not at work is in the Break
 * Area). Each place is one agent's at a time: a seat on the sofa, a side of the ping-pong table,
 * the coffee machine. Places and their activities are PROPOSED.
 *
 * MEMORY is a robot: it takes the standing places, and its own charging pad, but never a seat.
 */

import type { Pose } from './floorPlan';
import type { AgentKind } from './roster';

/** What an agent does at a place: rest (sit or stand), play, sip a drink, or charge. */
export type Activity = 'rest' | 'play' | 'sip' | 'charge';

export interface Spot {
  id: string;
  x: number;
  z: number;
  /** Radians about +y; 0 faces +z (south). */
  facing: number;
  pose: Pose;
  activity: Activity;
}

const QUARTER = Math.PI / 2;
const NORTH = Math.PI;

export const BREAK_SPOTS: readonly Spot[] = [
  { id: 'coffee', x: 23, z: 9.5, facing: NORTH, pose: 'stand', activity: 'sip' },
  { id: 'water', x: 24.35, z: 9.35, facing: NORTH, pose: 'stand', activity: 'sip' },
  { id: 'fridge', x: 25.3, z: 9.45, facing: NORTH, pose: 'stand', activity: 'sip' },
  { id: 'arcade', x: 29.6, z: 9.45, facing: NORTH, pose: 'stand', activity: 'play' },
  { id: 'vending', x: 30.45, z: 9.4, facing: QUARTER, pose: 'stand', activity: 'sip' },
  { id: 'charger', x: 26.9, z: 10, facing: 0, pose: 'stand', activity: 'charge' },
  { id: 'ping-pong-west', x: 27.45, z: 11.4, facing: QUARTER, pose: 'stand', activity: 'play' },
  { id: 'ping-pong-east', x: 30.55, z: 11.4, facing: -QUARTER, pose: 'stand', activity: 'play' },
  { id: 'window', x: 31.35, z: 12.35, facing: QUARTER, pose: 'stand', activity: 'rest' },
  { id: 'sofa-north', x: 25.82, z: 12.7, facing: -QUARTER, pose: 'sit', activity: 'rest' },
  { id: 'sofa-middle', x: 25.82, z: 13.3, facing: -QUARTER, pose: 'sit', activity: 'rest' },
  { id: 'sofa-south', x: 25.82, z: 13.9, facing: -QUARTER, pose: 'sit', activity: 'rest' },
  { id: 'armchair', x: 24.2, z: 14.4, facing: NORTH, pose: 'sit', activity: 'rest' },
  { id: 'bean-bag-lounge', x: 23.1, z: 14.45, facing: NORTH, pose: 'sit', activity: 'rest' },
  { id: 'bean-bag-games', x: 27.7, z: 14.3, facing: NORTH, pose: 'sit', activity: 'rest' },
  { id: 'bean-bag-cafe', x: 28.75, z: 14.35, facing: NORTH, pose: 'sit', activity: 'rest' },
  { id: 'cafe-west', x: 29.55, z: 13.7, facing: QUARTER, pose: 'sit', activity: 'rest' },
  { id: 'cafe-east', x: 31.05, z: 13.7, facing: -QUARTER, pose: 'sit', activity: 'rest' },
];

/** Whether an agent of this kind may take the place. */
export function suits(kind: AgentKind, spot: Spot): boolean {
  if (kind === 'memory') return spot.pose === 'stand';
  return spot.activity !== 'charge';
}
