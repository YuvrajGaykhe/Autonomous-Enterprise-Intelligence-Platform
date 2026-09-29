/**
 * Click targets (spec §9, §8.1): an invisible box around each agent, the CEO's desk and
 * SIGNALS_AGENT's board. A click opens the agent's panel, or the CEO inbox; a drag is not a click.
 */

import type { ThreeEvent } from '@react-three/fiber';
import { useThree } from '@react-three/fiber';

import type { Seat } from '@/domain/floorPlan';
import type { WorldAgent } from '@/office/worldTypes';

import { BOARD_ITEM } from './SignalsBoard';

/** How far, in pixels, the pointer may move between press and release for a click. */
const CLICK_SLOP = 5;

type Box = { at: [number, number, number]; size: [number, number, number] };

const CEO_DESK: Box = { at: [28, 0.7, 3.9], size: [2.4, 1.4, 2.2] };

function Target({ box, label, onOpen }: { box: Box; label: string; onOpen: () => void }) {
  const gl = useThree((state) => state.gl);
  return (
    <mesh
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
  seats,
  onOpenAgent,
  onOpenInbox,
}: {
  agents: readonly WorldAgent[];
  seats: ReadonlyMap<string, Seat>;
  onOpenAgent: (agentId: string) => void;
  onOpenInbox: () => void;
}) {
  return (
    <>
      {agents.map(({ agent }) => {
        if (agent.kind === 'ceo') {
          return <Target key={agent.id} box={CEO_DESK} label="hitbox:ceo" onOpen={onOpenInbox} />;
        }
        const seat = seats.get(agent.id);
        if (seat === undefined) return null;
        const tall = agent.kind === 'memory' ? 1.9 : seat.pose === 'sit' ? 1.6 : 1.75;
        return (
          <Target
            key={agent.id}
            box={{ at: [seat.x, tall / 2, seat.z], size: [0.9, tall, 0.9] }}
            label={`hitbox:${agent.id}`}
            onOpen={() => onOpenAgent(agent.id)}
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
