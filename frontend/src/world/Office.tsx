/**
 * The 3D office (spec §9; D-F-5, D-F-12): the lazy world chunk. Rooms, furniture and agents are
 * procedural parts drawn as a few instanced meshes, under a 3/4 orthographic camera and, unless
 * Smooth is chosen, three's pixel pass. Every value it shows arrives in its props, computed from
 * API responses by the office page (D-F-1).
 *
 * Nothing moves on its own in F3: agents sit or stand at their places. With `?still=1` the world
 * renders only when something changes, so screenshots are stable.
 */

import { Canvas, useFrame } from '@react-three/fiber';
import { useMemo, useRef, useState } from 'react';

import type { Seat } from '@/domain/floorPlan';

import { FURNITURE, connectorProps, seatsFor } from '@/domain/floorPlan';
import { yawDegrees } from '@/domain/officeCamera';
import { LOOKS } from '@/domain/agentLook';
import type { WorldProps } from '@/office/worldTypes';
import { useCamera } from '@/state/camera';

import { Batch } from './Batch';
import { CameraRig } from './CameraRig';
import { Hitboxes } from './Hitboxes';
import { bodyFor } from './kit/characters';
import { floorParts, groundParts, wallParts } from './kit/building';
import { bulbParts, GLOW_HEX, noteParts, trayParts } from './kit/dynamic';
import { furnitureParts } from './kit/furniture';
import { outlined } from './kit/parts';
import { Lighting } from './Lighting';
import { LabelLayer, LabelProjector } from './LabelLayer';
import { labelAnchors, WorldLabels } from './Overlays';
import { PerfOverlay, PerfProbe } from './Perf';
import { PixelRenderer } from './PixelRenderer';
import { Rings } from './Rings';
import { SignalsBoard } from './SignalsBoard';

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
  seats: ReadonlyMap<string, Seat>;
  layer: LabelLayer;
  labelVersion: string;
}

function Scene(props: SceneProps) {
  const { agents, pixel, seats } = props;
  const quarterTurns = useCamera((state) => state.quarterTurns);
  const zoomIndex = useCamera((state) => state.zoomIndex);
  const yaw = yawDegrees(quarterTurns);

  const bodies = useMemo(
    () =>
      new Map(
        agents.map((world) => {
          const seat = seats.get(world.agent.id);
          return [
            world.agent.id,
            seat === undefined ? null : bodyFor(world.agent.id, world.agent.kind, seat),
          ];
        }),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [seats],
  );

  const ground = useMemo(() => groundParts(), []);
  const floor = useMemo(() => floorParts(), []);
  const walls = useMemo(() => wallParts(yaw), [yaw]);
  const furniture = useMemo(
    () => [
      ...FURNITURE.flatMap(furnitureParts),
      ...agents
        .filter((world) => world.agent.kind === 'connector')
        .flatMap((world) => {
          const seat = seats.get(world.agent.id);
          return seat === undefined ? [] : connectorProps(seat).flatMap(furnitureParts);
        }),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [seats],
  );

  const glowing = agents
    .filter((world) => LOOKS[world.state].glow)
    .map((world) => world.agent.id)
    .join(' ');
  const characters = useMemo(
    () => [
      ...[...bodies.values()].flatMap((body) => body?.parts ?? []),
      ...[...bodies.entries()]
        .filter(([id]) => glowing.split(' ').includes(id))
        .flatMap(([, body]) => outlined(body?.parts ?? [], GLOW_HEX)),
    ],
    [bodies, glowing],
  );
  const states = agents.map((world) => `${world.agent.id}:${world.state}`).join(' ');
  const bulbs = useMemo(
    () => bulbParts(agents, bodies),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [bodies, states],
  );
  const tray = useMemo(() => trayParts(props.trayCount), [props.trayCount]);
  const noteKey = props.notes.map((note) => note.decision).join(' ');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const notes = useMemo(() => noteParts(props.notes), [noteKey]);

  return (
    <>
      <color attach="background" args={['#2b2622']} />
      <Lighting />
      <CameraRig pixel={pixel} animate={props.animate} />
      <Batch parts={ground} shadows="receive" />
      <Batch parts={floor} shadows="receive" />
      <Batch parts={walls} />
      <Batch parts={furniture} />
      <Batch parts={characters} shadows="cast" />
      <Batch parts={bulbs} shadows="none" />
      <Batch parts={tray} shadows="none" />
      <Batch parts={notes} shadows="none" />
      <SignalsBoard board={props.board} yaw={yaw} pixel={pixel} />
      <Rings
        seats={seats}
        openAgentId={props.openAgentId}
        highlightedAgentId={props.highlightedAgentId}
        animate={props.animate}
      />
      <Hitboxes
        agents={agents}
        seats={seats}
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
  const [layer] = useState(() => new LabelLayer());
  const rosterKey = props.agents.map((world) => world.agent.id).join(' ');
  // The seats depend on the roster alone, not on the agents' states.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const seats = useMemo(() => seatsFor(props.agents.map((world) => world.agent)), [rosterKey]);
  const anchors = useMemo(() => labelAnchors(props.agents, seats), [props.agents, seats]);
  layer.anchors.clear();
  for (const [id, anchor] of anchors) layer.anchors.set(id, anchor);
  const labelVersion = props.agents
    .map((world) => `${world.agent.id}:${world.state}:${world.bubble ?? ''}`)
    .join(' ');
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
          seats={seats}
          layer={layer}
          labelVersion={labelVersion}
        />
      </Canvas>
      <WorldLabels
        layer={layer}
        agents={props.agents}
        onOpenAgent={props.onOpenAgent}
        onOpenInbox={props.onOpenInbox}
      />
      {props.perf && <PerfOverlay />}
    </>
  );
}
