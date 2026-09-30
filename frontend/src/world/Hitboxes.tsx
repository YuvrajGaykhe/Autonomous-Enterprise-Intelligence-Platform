/**
 * Click targets (spec §9, §8.1): an invisible box around each agent, which follows the agent as it
 * walks, and fixed ones on the CEO's desk and SIGNALS_AGENT's board. A click opens the agent's
 * panel, or the CEO inbox; a drag is not a click.
 */

import type { ThreeEvent } from '@react-three/fiber';
import { useFrame, useThree } from '@react-three/fiber';
import { useRef } from 'react';
import type { Mesh } from 'three';

import type { WorldAgent } from '@/office/worldTypes';

import type { BodyPosition } from './Crowd';
import { BOARD_ITEM } from './SignalsBoard';

/** How far, in pixels, the pointer may move between press and release for a click. */
const CLICK_SLOP = 5;

type Box = { at: [number, number, number]; size: [number, number, number] };

const CEO_DESK: Box = { at: [28, 0.7, 3.9], size: [2.4, 1.4, 2.2] };

function Target({
  box,
  label,
  onOpen,
  follow,
}: {
  box: Box;
  label: string;
  onOpen: () => void;
  /** Where the agent is now; the box moves with it. */
  follow?: () => BodyPosition | undefined;
}) {
  const gl = useThree((state) => state.gl);
  const mesh = useRef<Mesh>(null);
  useFrame(() => {
    const position = follow?.();
    if (position === undefined || mesh.current === null) return;
    mesh.current.position.set(position.x, position.top / 2, position.z);
    mesh.current.scale.set(1, Math.max(0.6, position.top) / box.size[1], 1);
  });
  return (
    <mesh
      ref={mesh}
      name={label}
      position={box.at}
      visible={false}
      onClick={(event: ThreeEvent<MouseEvent>) => {
        if (event.delta > CLICK_SLOP) return;
        event.stopPropagation();
        onOpen();
      }}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => {
        event.stopPropagation();
        gl.domElement.style.cursor = 'pointer';
      }}
      onPointerOut={() => {
        gl.domElement.style.cursor = '';
      }}
    >
      <boxGeometry args={box.size} />
    </mesh>
  );
}

export function Hitboxes({
  agents,
  positions,
  onOpenAgent,
  onOpenInbox,
}: {
  agents: readonly WorldAgent[];
  positions: ReadonlyMap<string, BodyPosition>;
  onOpenAgent: (agentId: string) => void;
  onOpenInbox: () => void;
}) {
  return (
    <>
      {agents.map(({ agent }) => {
        if (agent.kind === 'ceo') {
          return <Target key={agent.id} box={CEO_DESK} label="hitbox:ceo" onOpen={onOpenInbox} />;
        }
        return (
          <Target
            key={agent.id}
            box={{ at: [0, -10, 0], size: [0.9, 1.75, 0.9] }}
            label={`hitbox:${agent.id}`}
            onOpen={() => onOpenAgent(agent.id)}
            follow={() => positions.get(agent.id)}
          />
        );
      })}
      {BOARD_ITEM !== undefined && (
        <Target
          box={{ at: [BOARD_ITEM.x, 1.3, BOARD_ITEM.z], size: [2.6, 2.6, 0.6] }}
          label="hitbox:signals-board"
          onOpen={() => onOpenAgent('signals')}
        />
      )}
    </>
  );
}
