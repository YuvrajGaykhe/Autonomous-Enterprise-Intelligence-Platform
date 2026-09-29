/**
 * The in-world labels (spec §9.3): each agent's name tag with its bulb glyph, its bubble ("…"
 * while its data loads, "?" while it waits for the CEO), and the room signs, locked rooms saying
 * which slice opens them (D-F-4). They are HTML over the canvas, so they are never pixelated. The
 * staff directory is their accessible twin, so they are hidden from assistive technology.
 */

import { Lock } from 'lucide-react';

import { COPY, fill } from '@/copy';
import { ROOM_LABEL_POINTS, type Seat } from '@/domain/floorPlan';
import { ROOMS } from '@/domain/roster';
import { StatusBadge } from '@/office/StatusBadge';
import type { WorldAgent } from '@/office/worldTypes';

import { bulbHeight } from './kit/characters';
import { Label, type Anchor, type LabelLayer } from './LabelLayer';

/** Where the CEO desk's tag stands: above the empty chair. */
const CEO_TAG_HEIGHT = 1.75;

function tagHeight(world: WorldAgent, seat: Seat): number {
  return world.agent.kind === 'ceo'
    ? CEO_TAG_HEIGHT
    : bulbHeight(world.agent.kind, seat.pose) + 0.32;
}

/** Every label's anchor in the world, by label id. */
export function labelAnchors(
  agents: readonly WorldAgent[],
  seats: ReadonlyMap<string, Seat>,
): Map<string, Anchor> {
  const anchors = new Map<string, Anchor>();
  for (const world of agents) {
    const seat = seats.get(world.agent.id);
    if (seat === undefined) continue;
    const height = tagHeight(world, seat);
    anchors.set(`tag:${world.agent.id}`, [seat.x, height, seat.z]);
    anchors.set(`bubble:${world.agent.id}`, [seat.x, height + 0.95, seat.z]);
  }
  for (const room of ROOMS) {
    const [x, z] = ROOM_LABEL_POINTS[room.id];
    anchors.set(`room:${room.id}`, [x, 0.05, z]);
  }
  return anchors;
}

export function WorldLabels({
  layer,
  agents,
  onOpenAgent,
  onOpenInbox,
}: {
  layer: LabelLayer;
  agents: readonly WorldAgent[];
  onOpenAgent: (agentId: string) => void;
  onOpenInbox: () => void;
}) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-20 overflow-hidden">
      {ROOMS.map((room) => (
        <Label key={room.id} layer={layer} id={`room:${room.id}`}>
          {room.opensWith === null ? (
            <span
              data-room={room.id}
              className="block rounded bg-[#fff8e7]/85 px-1.5 font-pixel text-[0.625rem] whitespace-nowrap text-[#4a3a28] uppercase"
            >
              {room.name}
            </span>
          ) : (
            <span
              data-room={room.id}
              className="flex flex-col items-center rounded-md border border-black/40 bg-[#f2c230]/90 px-2 py-0.5 font-pixel text-[0.625rem] leading-tight whitespace-nowrap text-black"
            >
              <span className="flex items-center gap-1 uppercase">
                <Lock aria-hidden="true" className="size-3" />
                {room.name}
              </span>
              <span>{fill(COPY.lockedRoom, { n: room.opensWith })}</span>
            </span>
          )}
        </Label>
      ))}
      {agents.map((world) => (
        <Label key={`tag:${world.agent.id}`} layer={layer} id={`tag:${world.agent.id}`}>
          <button
            type="button"
            tabIndex={-1}
            data-agent-tag={world.agent.id}
            onClick={() =>
              world.agent.kind === 'ceo' ? onOpenInbox() : onOpenAgent(world.agent.id)
            }
            className="pointer-events-auto flex items-center gap-1 rounded-full bg-black/85 py-0.5 pr-2 pl-0.5 font-pixel text-[0.625rem] whitespace-nowrap text-white shadow-md hover:bg-black"
          >
            <StatusBadge state={world.state} />
            {world.agent.tag}
          </button>
        </Label>
      ))}
      {agents.map((world) => (
        <Label key={`bubble:${world.agent.id}`} layer={layer} id={`bubble:${world.agent.id}`}>
          <span
            data-bubble={world.bubble ?? 'none'}
            className={
              world.bubble === null
                ? 'hidden'
                : 'block rounded-md border-2 border-black bg-white px-1.5 font-pixel text-xs leading-5 text-black shadow'
            }
          >
            {world.bubble === 'waiting' ? '?' : '…'}
          </span>
        </Label>
      ))}
    </div>
  );
}
