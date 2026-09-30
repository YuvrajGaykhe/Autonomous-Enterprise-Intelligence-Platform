/**
 * The 3D office (spec §9; D-F-5, D-F-12): the lazy world chunk. Rooms, furniture and agents are
 * procedural parts drawn as a few instanced meshes, under a 3/4 orthographic camera and, unless
 * Smooth is chosen, three's pixel pass. Every value it shows arrives in its props, computed from
 * API responses by the office page (D-F-1).
 *
 * Agents walk (F4; the owner's ruling): idle ones live in the Break Area, and a show's cues send
 * them to their desks, to each other and to the CEO's tray, under neon arrows. With `?still=1`
 * nobody walks, idle agents keep their first places, and the world renders only when something
 * changes, so screenshots are stable.
 */

import { Canvas, useFrame } from '@react-three/fiber';
import { useMemo, useRef, useState } from 'react';

import { AMBIENT_DWELL, type Dwell } from '@/domain/ambient';
import { officeLayout, type OfficeLayout } from '@/domain/layout';
import { officeFurniture } from '@/domain/floorPlan';
import { yawDegrees } from '@/domain/officeCamera';
import type { WorldProps } from '@/office/worldTypes';
import { useCamera } from '@/state/camera';

import { Arrows } from './Arrows';
import { Batch } from './Batch';
import { CameraRig } from './CameraRig';
import { Crowd, type BodyPosition } from './Crowd';
import { Hitboxes } from './Hitboxes';
import { floorParts, groundParts, wallParts } from './kit/building';
import { noteParts, trayParts } from './kit/dynamic';
import { furnitureParts } from './kit/furniture';
import { Lighting } from './Lighting';
import { LabelLayer, LabelProjector } from './LabelLayer';
import { labelAnchors, WorldLabels } from './Overlays';
import { PerfOverlay, PerfProbe } from './Perf';
import { PixelRenderer } from './PixelRenderer';
import { Rings } from './Rings';
import { SignalsBoard } from './SignalsBoard';
import { Stamp } from './Stamp';

/** Idle agents keep strolling, for the performance record's "every agent moving" (§9.10). */
const RESTLESS: Dwell = [0, 0.3];

/** Calls `onReady` once, after the first frame. */
function FirstFrame({ onReady }: { onReady: () => void }) {
  const done = useRef(false);
  useFrame(() => {
    if (done.current) return;
    done.current = true;
    onReady();
  });
  return null;
}

interface SceneProps extends WorldProps {
  animate: boolean;
  dwell: Dwell | null;
  layout: OfficeLayout;
  positions: Map<string, BodyPosition>;
  layer: LabelLayer;
  labelVersion: string;
}

function Scene(props: SceneProps) {
  const { agents, pixel, layout } = props;
  const quarterTurns = useCamera((state) => state.quarterTurns);
  const zoomIndex = useCamera((state) => state.zoomIndex);
  const yaw = yawDegrees(quarterTurns);

  const ground = useMemo(() => groundParts(), []);
  const floor = useMemo(() => floorParts(), []);
  const walls = useMemo(() => wallParts(yaw), [yaw]);
  const furniture = useMemo(() => officeFurniture(layout.roster).flatMap(furnitureParts), [layout]);
  const tray = useMemo(() => trayParts(props.trayCount), [props.trayCount]);
  const noteKey = props.notes.map((note) => note.decision).join(' ');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const notes = useMemo(() => noteParts(props.notes), [noteKey]);

  return (
    <>
      <color attach="background" args={['#2b2622']} />
      <Lighting />
      <CameraRig pixel={pixel} animate={props.animate} />
      <Crowd
        agents={agents}
        layout={layout}
        animate={props.animate}
        dwell={props.dwell}
        positions={props.positions}
        layer={props.layer}
      />
      <Batch parts={ground} shadows="receive" />
      <Batch parts={floor} shadows="receive" />
      <Batch parts={walls} />
      <Batch parts={furniture} />
      <Batch parts={tray} shadows="none" />
      <Batch parts={notes} shadows="none" />
      <Arrows arrows={props.arrows} animate={props.animate} layer={props.layer} />
      <Stamp stamp={props.stamp} trayCount={props.trayCount} animate={props.animate} />
      <SignalsBoard board={props.board} yaw={yaw} pixel={pixel} />
      <Rings
        seats={layout.seats}
        positions={props.positions}
        openAgentId={props.openAgentId}
        highlightedAgentId={props.highlightedAgentId}
        animate={props.animate}
      />
      <Hitboxes
        agents={agents}
        positions={props.positions}
        onOpenAgent={props.onOpenAgent}
        onOpenInbox={props.onOpenInbox}
      />
      <LabelProjector layer={props.layer} version={props.labelVersion} />
      {pixel && <PixelRenderer zoomIndex={zoomIndex} />}
      {props.perf && <PerfProbe />}
      <FirstFrame onReady={props.onReady} />
    </>
  );
}

export default function Office(props: WorldProps) {
  const animate = !props.still && !props.reducedMotion;
  const dwell = props.still || props.reducedMotion ? null : props.perf ? RESTLESS : AMBIENT_DWELL;
  const [layer] = useState(() => new LabelLayer());
  const [positions] = useState(() => new Map<string, BodyPosition>());
  const rosterKey = props.agents.map((world) => world.agent.id).join(' ');
  // The layout depends on the roster alone, not on the agents' states.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const layout = useMemo(() => officeLayout(props.agents.map((world) => world.agent)), [rosterKey]);
  // The fixed anchors: room signs and the CEO desk. A body is anchored by the crowd each frame;
  // until its first frame, at its desk.
  for (const [id, anchor] of labelAnchors(props.agents, layout.seats))
    if (!layer.anchors.has(id)) layer.anchors.set(id, anchor);
  const labelVersion = [
    ...props.agents.map(
      (world) =>
        `${world.agent.id}:${world.state}:${world.bubble ?? ''}:${world.cue?.caption ?? ''}`,
    ),
    ...props.arrows.map((arrow) => arrow.id),
  ].join(' ');
  return (
    <>
      <Canvas
        orthographic
        shadows="percentage"
        flat
        dpr={[1, 2]}
        frameloop={props.still && !props.perf ? 'demand' : 'always'}
        gl={{ antialias: true, powerPreference: 'high-performance' }}
        camera={{ position: [40, 30, 40], zoom: 20, near: 0.1, far: 200 }}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener('webglcontextlost', props.onContextLost);
        }}
        aria-hidden="true"
        className="size-full"
      >
        <Scene
          {...props}
          animate={animate}
          dwell={dwell}
          layout={layout}
          positions={positions}
          layer={layer}
          labelVersion={labelVersion}
        />
      </Canvas>
      <WorldLabels
        layer={layer}
        agents={props.agents}
        arrows={props.arrows}
        onOpenAgent={props.onOpenAgent}
        onOpenInbox={props.onOpenInbox}
      />
      {props.perf && <PerfOverlay />}
    </>
  );
}
