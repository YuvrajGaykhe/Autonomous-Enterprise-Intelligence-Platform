/**
 * The agents in motion (spec §9.4, §9.7, §9.9, §9.11; the owner's F4 ruling).
 *
 * An agent the show does not need is idle in the Break Area: it takes a free place there, stays a
 * while, and strolls to another (`AmbientPlanner`). An agent the show needs walks to where its cue
 * says, along the walk grid: to its desk to work, to the next stage's agent to hand over its
 * result, to the debate table for a conflict, to the CEO's tray with a brief. Arrived, it sits or
 * stands as its place requires, and types, presents, cheers, plays or sips.
 *
 * Every body is drawn with a few instanced meshes, rewritten each frame. The working glow is a
 * hull of the same parts; the antenna bulb follows the state. Each frame also moves the body's
 * name tag and bubble, and the positions the click targets and the open panel's ring follow.
 *
 * Under reduced motion and `still` nobody walks: every body is placed where it should be, and no
 * limb swings. `still` also keeps idle agents at their first place, so screenshots are stable.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo } from 'react';
import { Color, Group, InstancedBufferAttribute, InstancedMesh, Matrix4 } from 'three';

import { LOOKS } from '@/domain/agentLook';
import { AmbientPlanner, type Dwell } from '@/domain/ambient';
import type { Activity } from '@/domain/breakArea';
import { placeSeat } from '@/domain/director';
import type { Seat } from '@/domain/floorPlan';
import type { OfficeLayout } from '@/domain/layout';
import type { AgentKind } from '@/domain/roster';
import { advance, arrived, paceFor, remaining, turnTowards, type Mover } from '@/domain/walker';
import { findPath } from '@/domain/walkGrid';
import type { WorldAgent } from '@/office/worldTypes';

import { rigFor, type Rig, type Segment } from './kit/characters';
import { BULB_HEX, GLOW_HEX } from './kit/dynamic';
import { limbs, segmentMatrices, segmentSet, type Animation } from './kit/motion';
import { box, type Finish, type Part, type Shape } from './kit/parts';
import type { LabelLayer } from './LabelLayer';
import { geometryFor, materialFor } from './materials';

/** Radians of the walk cycle per world unit walked. */
const STRIDE = 3.4;
/** The most time one frame may walk, in seconds, so a long pause is not one jump. */
const MAX_STEP = 0.5;
/** How much larger the glow hull is than the body. */
const HULL = 1.14;
/** The tag floats this far above the bulb, the bubble this far above the tag. */
const TAG_LIFT = 0.32;
const BUBBLE_LIFT = 0.95;

/** Where a body is, for the click targets, the ring and the labels. */
export interface BodyPosition {
  x: number;
  z: number;
  /** The height of the top of the body. */
  top: number;
}

interface Walker extends Mover {
  kind: AgentKind;
  /** The identity of where it is heading, to notice a new goal. */
  key: string;
  goal: Seat;
  activity: Activity | null;
  /** Heading for a Break Area place, whose arrival the planner hears of. */
  toBreak: boolean;
  phase: number;
  rigs: Record<'stand' | 'sit', Rig>;
  segments: Record<Segment, Matrix4>;
}

/** A part's colour, parsed once. */
const colours = new Map<string, Color>();
function colourOf(hex: string): Color {
  let colour = colours.get(hex);
  if (colour === undefined) {
    colour = new Color(hex);
    colours.set(hex, colour);
  }
  return colour;
}

const SHEET: Part = box('#fbfaf5', [0.3, 0.02, 0.4], [0, 0.58, 0.32], [0.5, 0, 0]);

// Scratch matrices, reused every frame.
const base = new Matrix4();
const joint = new Matrix4();
const placedPart = new Matrix4();
const hulled = new Matrix4();
const HULL_SCALE = new Matrix4().makeScale(HULL, HULL, HULL);
const BULB_SCALE = new Matrix4().makeScale(0.14, 0.14, 0.14);

interface Slot {
  mesh: InstancedMesh;
  count: number;
}

function slotKey(shape: Shape, finish: Finish): string {
  return `${shape}:${finish}`;
}

/** How many instances of each shape and finish the crowd can ever need. */
function capacities(rigs: readonly Record<'stand' | 'sit', Rig>[]): Map<string, number> {
  const totals = new Map<string, number>();
  const add = (key: string, count: number) => totals.set(key, (totals.get(key) ?? 0) + count);
  for (const pair of rigs) {
    const most = new Map<string, number>();
    for (const rig of [pair.stand, pair.sit]) {
      const counts = new Map<string, number>();
      for (const item of rig.parts) {
        counts.set(
          slotKey(item.shape, item.finish),
          (counts.get(slotKey(item.shape, item.finish)) ?? 0) + 1,
        );
        counts.set(
          slotKey(item.shape, 'outline'),
          (counts.get(slotKey(item.shape, 'outline')) ?? 0) + 1,
        );
      }
      for (const [key, count] of counts) most.set(key, Math.max(most.get(key) ?? 0, count));
    }
    for (const [key, count] of most) add(key, count);
    // The bulb, the carried sheet and the sheet's hull.
    add(slotKey('sphere', 'glow'), 1);
    add(slotKey('box', 'toon'), 1);
    add(slotKey('box', 'outline'), 1);
  }
  return totals;
}

export function Crowd({
  agents,
  layout,
  animate,
  dwell,
  positions,
  layer,
}: {
  agents: readonly WorldAgent[];
  layout: OfficeLayout;
  /** Walk and swing limbs; false under reduced motion and `still`, which place bodies at once. */
  animate: boolean;
  /** How long idle agents stay at a place; null keeps them at their first one (`still`). */
  dwell: Dwell | null;
  positions: Map<string, BodyPosition>;
  layer: LabelLayer;
}) {
  const invalidate = useThree((state) => state.invalidate);
  const bodies = agents.filter((world) => world.agent.kind !== 'ceo');
  const rosterKey = bodies.map((world) => world.agent.id).join(' ');
  const dwellKey = dwell === null ? 'still' : dwell.join(' ');

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const planner = useMemo(() => new AmbientPlanner(dwell), [dwellKey]);
  const walkers = useMemo(() => new Map<string, Walker>(), []);

  const { group, slots } = useMemo(() => {
    const rigs = bodies.map((world) => ({
      stand: rigFor(world.agent.id, world.agent.kind, 'stand') as Rig,
      sit: rigFor(world.agent.id, world.agent.kind, 'sit') as Rig,
    }));
    const built = new Group();
    const byKey = new Map<string, Slot>();
    for (const [key, capacity] of capacities(rigs)) {
      const [shape, finish] = key.split(':') as [Shape, Finish];
      const mesh = new InstancedMesh(geometryFor(shape), materialFor(finish), capacity);
      mesh.instanceColor = new InstancedBufferAttribute(new Float32Array(capacity * 3), 3);
      mesh.count = 0;
      mesh.frustumCulled = false;
      mesh.castShadow = finish === 'toon';
      built.add(mesh);
      byKey.set(key, { mesh, count: 0 });
    }
    return { group: built, slots: byKey };
    // The meshes depend on the roster alone.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rosterKey]);

  useEffect(
    () => () => {
      for (const slot of slots.values()) slot.mesh.dispose();
    },
    [slots],
  );

  // A new cue in `still` or demand mode needs a frame to show it.
  useEffect(() => invalidate(), [agents, invalidate]);

  useFrame((_, delta) => {
    const nowMs = performance.now();
    const now = nowMs / 1000;
    // A slow or throttled frame still walks its full time, up to half a second at once.
    const seconds = Math.min(delta, MAX_STEP);
    for (const slot of slots.values()) slot.count = 0;

    const put = (shape: Shape, finish: Finish, matrix: Matrix4, colour: Color) => {
      const slot = slots.get(slotKey(shape, finish));
      if (slot === undefined || slot.count >= slot.mesh.instanceMatrix.count) return;
      slot.mesh.setMatrixAt(slot.count, matrix);
      slot.mesh.setColorAt(slot.count, colour);
      slot.count += 1;
    };

    for (const body of bodies) {
      const id = body.agent.id;
      const cue = body.cue;

      // Where it should be.
      let goal: Seat;
      let key: string;
      let activity: Activity | null = null;
      let toBreak = false;
      if (cue === undefined || cue.place.kind === 'break') {
        const spot = planner.spotFor(id, body.agent.kind, now);
        goal = spot ?? (layout.seats.get(id) as Seat);
        key = spot === null ? 'desk' : `break:${spot.id}`;
        activity = spot?.activity ?? null;
        toBreak = spot !== null;
      } else {
        planner.release(id);
        goal = placeSeat(layout, id, cue.place);
        key = `${cue.place.kind}:${goal.x},${goal.z}`;
      }

      let walker = walkers.get(id);
      if (walker === undefined) {
        walker = {
          kind: body.agent.kind,
          x: goal.x,
          z: goal.z,
          facing: goal.facing,
          path: [[goal.x, goal.z]],
          next: 1,
          key,
          goal,
          activity,
          toBreak,
          phase: 0,
          rigs: {
            stand: rigFor(id, body.agent.kind, 'stand') as Rig,
            sit: rigFor(id, body.agent.kind, 'sit') as Rig,
          },
          segments: segmentSet(),
        };
        walkers.set(id, walker);
        if (toBreak) planner.arrived(id, now);
      }
      if (walker.key !== key) {
        walker.key = key;
        walker.goal = goal;
        walker.activity = activity;
        walker.toBreak = toBreak;
        walker.path = findPath(layout.grid, [walker.x, walker.z], [goal.x, goal.z]) ?? [
          [walker.x, walker.z],
          [goal.x, goal.z],
        ];
        walker.next = 1;
      }

      // Walk, or settle.
      if (!arrived(walker)) {
        if (animate) {
          const secondsLeft = cue?.arriveBy == null ? null : (cue.arriveBy - nowMs) / 1000;
          const pace = paceFor(remaining(walker), secondsLeft);
          walker.phase += advance(walker, pace * seconds, seconds) * STRIDE;
        } else {
          const last = walker.path.at(-1) ?? [goal.x, goal.z];
          walker.x = last[0];
          walker.z = last[1];
          walker.next = walker.path.length;
        }
        if (arrived(walker) && walker.toBreak) planner.arrived(id, now);
      } else {
        walker.facing = animate ? turnTowards(walker.facing, goal.facing, seconds) : goal.facing;
      }

      // Its pose.
      const moving = !arrived(walker);
      const cheering = cue?.cheer === true;
      const sitting = !moving && !cheering && goal.pose === 'sit';
      const rig = sitting ? walker.rigs.sit : walker.rigs.stand;
      let animation: Animation;
      if (moving) animation = cue?.carrying === true ? 'carryWalk' : 'walk';
      else if (cheering) animation = 'cheer';
      else if (body.state === 'WORKING') animation = sitting ? 'type' : 'work';
      else if (body.state === 'HANDOFF') animation = cue?.carrying === true ? 'carry' : 'present';
      else if (cue === undefined && walker.activity === 'play') animation = 'play';
      else if (cue === undefined && walker.activity === 'sip') animation = 'sip';
      else animation = 'idle';
      const pose = limbs(animation, walker.phase, now, animate);
      segmentMatrices(rig, pose, walker.segments);

      // Its parts.
      base.makeRotationY(walker.facing).setPosition(walker.x, pose.bob, walker.z);
      const glow = LOOKS[body.state].glow;
      const glowColour = colourOf(GLOW_HEX);
      const draw = (item: Part, segment: Segment) => {
        joint.multiplyMatrices(base, walker.segments[segment]);
        placedPart.multiplyMatrices(joint, item.matrix);
        put(item.shape, item.finish, placedPart, colourOf(item.color));
        if (glow)
          put(item.shape, 'outline', hulled.multiplyMatrices(placedPart, HULL_SCALE), glowColour);
      };
      for (const item of rig.parts) draw(item, item.segment);
      if (cue?.carrying === true) draw(SHEET, 'body');
      placedPart.makeTranslation(walker.x, rig.bulb + pose.bob, walker.z).multiply(BULB_SCALE);
      put('sphere', 'glow', placedPart, colourOf(BULB_HEX[LOOKS[body.state].bulb]));

      // Its labels, click target and ring.
      const top = rig.bulb + pose.bob;
      layer.anchors.set(`tag:${id}`, [walker.x, top + TAG_LIFT, walker.z]);
      layer.anchors.set(`bubble:${id}`, [walker.x, top + TAG_LIFT + BUBBLE_LIFT, walker.z]);
      const position = positions.get(id);
      if (position === undefined) positions.set(id, { x: walker.x, z: walker.z, top });
      else {
        position.x = walker.x;
        position.z = walker.z;
        position.top = top;
      }
    }

    for (const slot of slots.values()) {
      slot.mesh.count = slot.count;
      slot.mesh.instanceMatrix.needsUpdate = true;
      if (slot.mesh.instanceColor !== null) slot.mesh.instanceColor.needsUpdate = true;
    }
  }, -1);

  return <primitive object={group} />;
}
