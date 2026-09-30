/**
 * The in-world labels (spec §9.3): each agent's name tag with its bulb glyph, its bubble ("…"
 * while its data loads, "?" while it waits for the CEO, a step's caption while it works or hands
 * over, §9.5), each arrow's label, and the room signs, locked rooms saying which slice opens them
 * (D-F-4). They are HTML over the canvas, so they are never pixelated. The staff directory is their
 * accessible twin, so they are hidden from assistive technology.
 *
 * A walking agent's tag and bubble follow it: the crowd moves their anchors every frame (F4).
 */

import { Lock } from 'lucide-react';

import { COPY, fill } from '@/copy';
import type { Arrow } from '@/domain/director';
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

/**
 * The anchors that stand still, by label id: the room signs, and the CEO desk's tag and bubble
 * over the empty chair. An agent with a body is anchored by the crowd, wherever it walks; until
 * its first frame, at its desk.
 */
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

/** What an agent's bubble says: its step's caption, else "?" or "…", else nothing. */
export function bubbleText(world: WorldAgent): string | null {
  const caption = world.cue?.caption ?? null;
  if (caption !== null && (world.state === 'WORKING' || world.state === 'HANDOFF')) return caption;
  if (world.bubble === 'waiting') return '?';
  if (world.bubble === 'loading') return '…';
  return null;
}

export function WorldLabels({
  layer,
  agents,
  arrows = [],
  onOpenAgent,
  onOpenInbox,
}: {
  layer: LabelLayer;
  agents: readonly WorldAgent[];
  arrows?: readonly Arrow[];
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
      {agents.map((world) => {
        // An agent on its break wears a smaller tag, so the Break Area's crowd stays legible.
        const resting = world.cue === undefined && world.agent.kind !== 'ceo';
        return (
          <Label key={`tag:${world.agent.id}`} layer={layer} id={`tag:${world.agent.id}`}>
            <button
              type="button"
              tabIndex={-1}
              data-agent-tag={world.agent.id}
              data-resting={resting ? 'true' : undefined}
              onClick={() =>
                world.agent.kind === 'ceo' ? onOpenInbox() : onOpenAgent(world.agent.id)
              }
              className={
                resting
                  ? 'pointer-events-auto flex items-center gap-0.5 rounded-full bg-black/75 py-px pr-1.5 pl-px font-pixel text-[0.5rem] whitespace-nowrap text-white shadow hover:bg-black'
                  : 'pointer-events-auto flex items-center gap-1 rounded-full bg-black/85 py-0.5 pr-2 pl-0.5 font-pixel text-[0.625rem] whitespace-nowrap text-white shadow-md hover:bg-black'
              }
            >
              <StatusBadge state={world.state} className={resting ? 'size-3 text-[0.5rem]' : ''} />
              {world.agent.tag}
            </button>
          </Label>
        );
      })}
      {agents.map((world) => {
        const text = bubbleText(world);
        const captioned = text !== null && text === (world.cue?.caption ?? null);
        return (
          <Label key={`bubble:${world.agent.id}`} layer={layer} id={`bubble:${world.agent.id}`}>
            <span
              data-bubble={captioned ? 'caption' : (world.bubble ?? 'none')}
              className={
                text === null
                  ? 'hidden'
                  : captioned
                    ? 'block max-w-56 rounded-md border-2 border-[#22d3ee] bg-[#0b1d26]/90 px-1.5 font-pixel text-[0.625rem] leading-4 whitespace-nowrap text-[#bff6ff] shadow'
                    : 'block rounded-md border-2 border-black bg-white px-1.5 font-pixel text-xs leading-5 text-black shadow'
              }
            >
              {text ?? '…'}
            </span>
          </Label>
        );
      })}
      {arrows.map((arrow) => (
        <Label key={`arrow:${arrow.id}`} layer={layer} id={`arrow:${arrow.id}`}>
          <span
            data-arrow={arrow.tone}
            className={
              arrow.tone === 'conflict'
                ? 'block rounded-full border-2 border-[#ef4444] bg-[#2a0d0d]/90 px-2 font-pixel text-[0.625rem] leading-4 whitespace-nowrap text-[#ffd0d0] shadow'
                : 'block rounded-full border-2 border-[#22d3ee] bg-[#0b1d26]/90 px-2 font-pixel text-[0.625rem] leading-4 whitespace-nowrap text-[#bff6ff] shadow'
            }
          >
            {arrow.label}
          </span>
        </Label>
      ))}
    </div>
  );
}
