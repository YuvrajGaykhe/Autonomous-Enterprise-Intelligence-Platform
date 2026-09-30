/**
 * Floor rings (spec §8.4): a white ring under the agent whose panel is open, which follows it as it
 * walks, and an amber ring that pulses under the desk an evidence link points at. The pulse stops
 * under reduced motion and `still`. Neither is the working glow, which only WORKING and HANDOFF
 * show (§9.3).
 */

import { useFrame } from '@react-three/fiber';
import { useRef } from 'react';
import type { Mesh } from 'three';

import type { Seat } from '@/domain/floorPlan';

import type { BodyPosition } from './Crowd';
import { geometryFor } from './materials';

const CEO_RING: Seat = { x: 28, z: 3.9, facing: 0, pose: 'sit' };

function Ring({
  seat,
  colour,
  size,
  pulse,
  follow,
}: {
  seat: Seat;
  colour: string;
  size: number;
  pulse: boolean;
  follow?: () => BodyPosition | undefined;
}) {
  const mesh = useRef<Mesh>(null);
  useFrame(({ clock }) => {
    if (mesh.current === null) return;
    const position = follow?.();
    if (position !== undefined) mesh.current.position.set(position.x, 0.04, position.z);
    if (!pulse) return;
    const scale = size * (1 + 0.08 * Math.sin(clock.elapsedTime * 5));
    mesh.current.scale.set(scale, scale, scale);
  });
  return (
    <mesh
      ref={mesh}
      geometry={geometryFor('torus')}
      position={[seat.x, 0.04, seat.z]}
      rotation={[Math.PI / 2, 0, 0]}
      scale={[size, size, size]}
    >
      <meshBasicMaterial color={colour} toneMapped={false} />
    </mesh>
  );
}

export function Rings({
  seats,
  positions,
  openAgentId,
  highlightedAgentId,
  animate,
}: {
  seats: ReadonlyMap<string, Seat>;
  positions: ReadonlyMap<string, BodyPosition>;
  openAgentId: string | null;
  highlightedAgentId: string | null;
  animate: boolean;
}) {
  const seatOf = (id: string | null) =>
    id === 'ceo' ? CEO_RING : id === null ? undefined : seats.get(id);
  const open = seatOf(openAgentId);
  const highlighted = seatOf(highlightedAgentId);
  return (
    <>
      {open !== undefined && (
        <Ring
          seat={open}
          colour="#ffffff"
          size={openAgentId === 'ceo' ? 2.4 : 1.2}
          pulse={false}
          follow={() => (openAgentId === null ? undefined : positions.get(openAgentId))}
        />
      )}
      {highlighted !== undefined && (
        <Ring seat={highlighted} colour="#fbbf24" size={1.5} pulse={animate} />
      )}
    </>
  );
}
