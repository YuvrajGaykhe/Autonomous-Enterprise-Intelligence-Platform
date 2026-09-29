/**
 * An agent's antenna bulb as a badge (spec §9.3): its colour always comes with its glyph, so
 * colour never carries the meaning alone (§10).
 */

import { LOOKS, type AgentState, type BulbColour } from '@/domain/agentLook';
import { cn } from '@/lib/utils';

const BULB_CLASS: Readonly<Record<BulbColour, string>> = {
  idle: 'bg-bulb-idle text-black',
  working: 'bg-bulb-working text-black',
  waiting: 'bg-bulb-waiting text-black',
  done: 'bg-bulb-done text-black',
  error: 'bg-bulb-error text-white',
};

export function StatusBadge({ state, className }: { state: AgentState; className?: string }) {
  const look = LOOKS[state];
  return (
    <span
      aria-hidden="true"
      data-bulb={look.bulb}
      className={cn(
        'inline-flex size-4 shrink-0 items-center justify-center rounded-full text-[0.625rem] leading-none font-bold',
        BULB_CLASS[look.bulb],
        className,
      )}
    >
      {look.glyph}
    </span>
  );
}
