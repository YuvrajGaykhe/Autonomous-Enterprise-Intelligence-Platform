/**
 * The neon arrows (spec §9.3, §9.5): cyan from an agent handing over its result to the agent who
 * takes it, red between the two sides of a conflict. Each is an arc of glowing chevrons flowing
 * from giver to taker, ending in a head; a conflict's arrow has a head at each end and does not
 * flow. Its label is the step's caption, a DOM label at the top of the arc. Under reduced motion
 * and `still` the chevrons stand still.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo } from 'react';
import {
  Color,
  Group,
  InstancedBufferAttribute,
  InstancedMesh,
  Matrix4,
  Quaternion,
  Vector3,
} from 'three';

import type { Arrow } from '@/domain/director';

import { arcPoint, arrowLabelAnchor } from './kit/arrows';
import type { LabelLayer } from './LabelLayer';
import { geometryFor, materialFor } from './materials';

export const ARROW_HEX: Readonly<Record<Arrow['tone'], string>> = {
  handoff: '#22d3ee',
  conflict: '#ef4444',
};

const SPACING = 0.42;
const FLOW = 1.6;
const CHEVRONS = 640;
const HEADS = 24;

const UP = new Vector3(0, 1, 0);
const FORWARD = new Vector3(0, 0, 1);
const point = new Vector3();
const ahead = new Vector3();
const tangent = new Vector3();
const turn = new Quaternion();
const matrix = new Matrix4();
const CHEVRON_SIZE = new Vector3(0.16, 0.05, 0.26);
const HEAD_SIZE = new Vector3(0.36, 0.42, 0.36);

const COLOURS: Readonly<Record<Arrow['tone'], Color>> = {
  handoff: new Color(ARROW_HEX.handoff),
  conflict: new Color(ARROW_HEX.conflict),
};
/** Where on the arc a head sits: at its very end. */
const HEAD_AT = 0.99;

const reversed = (arrow: Arrow): Arrow => ({ ...arrow, from: arrow.to, to: arrow.from });

/** One chevron or head `at` along the arc, turned so `axis` follows the arc. */
function place(
  target: InstancedMesh,
  index: number,
  at: number,
  arrow: Arrow,
  size: Vector3,
  axis: Vector3,
): void {
  point.set(...arcPoint(arrow, at));
  ahead.set(...arcPoint(arrow, Math.min(1, at + 0.01)));
  tangent.subVectors(ahead, point).normalize();
  turn.setFromUnitVectors(axis, tangent);
  target.setMatrixAt(index, matrix.compose(point, turn, size));
  target.setColorAt(index, COLOURS[arrow.tone]);
}

function mesh(shape: 'box' | 'cone', capacity: number): InstancedMesh {
  const built = new InstancedMesh(geometryFor(shape), materialFor('glow'), capacity);
  built.instanceColor = new InstancedBufferAttribute(new Float32Array(capacity * 3), 3);
  built.count = 0;
  built.frustumCulled = false;
  return built;
}

export function Arrows({
  arrows,
  animate,
  layer,
}: {
  arrows: readonly Arrow[];
  animate: boolean;
  layer: LabelLayer;
}) {
  const invalidate = useThree((state) => state.invalidate);
  const { group, chevrons, heads } = useMemo(() => {
    const built = new Group();
    const chevronMesh = mesh('box', CHEVRONS);
    const headMesh = mesh('cone', HEADS);
    built.add(chevronMesh, headMesh);
    return { group: built, chevrons: chevronMesh, heads: headMesh };
  }, []);

  useEffect(
    () => () => {
      chevrons.dispose();
      heads.dispose();
    },
    [chevrons, heads],
  );

  useEffect(() => {
    for (const arrow of arrows) layer.anchors.set(`arrow:${arrow.id}`, arrowLabelAnchor(arrow));
    invalidate();
  }, [arrows, layer, invalidate]);

  useFrame(({ clock }) => {
    let chevronCount = 0;
    let headCount = 0;
    for (const arrow of arrows) {
      const length = Math.hypot(arrow.to[0] - arrow.from[0], arrow.to[1] - arrow.from[1]);
      const arc = Math.max(0.5, length * 1.25);
      const flow = animate && arrow.tone === 'handoff' ? (clock.elapsedTime * FLOW) % SPACING : 0;
      for (let along = flow; along < arc - 0.3 && chevronCount < CHEVRONS; along += SPACING) {
        place(chevrons, chevronCount, along / arc, arrow, CHEVRON_SIZE, FORWARD);
        chevronCount += 1;
      }
      const ends = arrow.tone === 'conflict' ? [arrow, reversed(arrow)] : [arrow];
      for (const end of ends) {
        if (headCount >= HEADS) break;
        place(heads, headCount, HEAD_AT, end, HEAD_SIZE, UP);
        headCount += 1;
      }
    }
    for (const target of [chevrons, heads]) {
      target.count = target === chevrons ? chevronCount : headCount;
      target.instanceMatrix.needsUpdate = true;
      if (target.instanceColor !== null) target.instanceColor.needsUpdate = true;
    }
  });

  return <primitive object={group} />;
}
