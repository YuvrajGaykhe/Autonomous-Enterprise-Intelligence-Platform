/**
 * The office's staff directory (spec §10): every agent the office shows, as a keyboard-reachable
 * list. Enter opens the agent's panel. It is the accessible path to everything the canvas shows:
 * each entry states the agent's state in words, the same state its bulb shows.
 */

import { Inbox } from 'lucide-react';
import { Link } from 'react-router';

import { COPY } from '@/copy';
import { addressOf } from '@/domain/views';

import { StatusBadge } from './StatusBadge';
import type { WorldAgent } from './worldTypes';

const entry =
  'flex w-full items-start gap-2 rounded-md px-2 py-1 text-left hover:bg-muted aria-[current=true]:bg-muted';

export function StaffDirectory({
  agents,
  search,
  openAgentId,
  inboxOpen,
  loadingConnectors,
}: {
  agents: readonly WorldAgent[];
  search: string;
  openAgentId: string | null;
  inboxOpen: boolean;
  loadingConnectors: boolean;
}) {
  return (
    <nav
      aria-label="Staff directory"
      className="flex w-60 shrink-0 flex-col gap-1 overflow-y-auto border-r bg-card p-2"
    >
      <h2 className="px-2 pt-1 font-pixel text-xs tracking-wide uppercase">Staff directory</h2>
      <ul className="space-y-0.5">
        <li>
          <Link
            to={addressOf('office', { kind: 'inbox' }, search)}
            aria-current={inboxOpen ? 'true' : undefined}
            className={entry}
          >
            <Inbox aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span className="text-sm font-medium">CEO inbox</span>
          </Link>
        </li>
        {agents.map(({ agent, state, detail }) => (
          <li key={agent.id}>
            <Link
              to={addressOf('office', { kind: 'agent', agentId: agent.id }, search)}
              aria-current={openAgentId === agent.id ? 'true' : undefined}
              className={entry}
              data-agent={agent.id}
            >
              <StatusBadge state={state} className="mt-0.5" />
              <span className="min-w-0">
                <span className="block font-pixel text-xs">{agent.tag}</span>
                <span className="block text-xs text-muted-foreground">
                  <span className="sr-only">: </span>
                  {detail}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {loadingConnectors && (
        <p className="px-2 text-xs text-muted-foreground">Loading the connectors…</p>
      )}
      <p className="px-2 pb-1 text-xs text-muted-foreground">{COPY.aboutAgents}</p>
    </nav>
  );
}
