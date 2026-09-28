/**
 * Classic view: the same data as the office, as plain pages (D-F-6, spec §8.1). Its navigation is
 * also the staff directory: every agent, reachable by keyboard (§10).
 */

import { NavLink, Outlet, useLocation } from 'react-router';

import { useRoster } from '@/data/useRoster';
import { cn } from '@/lib/utils';

function Item({ to, end = false, children }: { to: string; end?: boolean; children: string }) {
  const { search } = useLocation();
  return (
    <li>
      <NavLink
        end={end}
        to={{ pathname: to, search }}
        className={({ isActive }) =>
          cn(
            'block rounded-md px-3 py-1.5 text-sm hover:bg-muted',
            isActive ? 'bg-muted font-medium' : '',
          )
        }
      >
        {children}
      </NavLink>
    </li>
  );
}

export function ClassicLayout() {
  const { roster, sources } = useRoster();
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4 md:flex-row">
      <nav aria-label="Classic view" className="md:w-52 md:shrink-0">
        <ul className="flex flex-wrap gap-1 md:flex-col">
          <Item to="/classic" end>
            Overview
          </Item>
          <Item to="/classic/inbox">CEO inbox</Item>
        </ul>
        <h2 className="mt-4 mb-1 px-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          Agents
        </h2>
        <ul aria-label="Staff directory" className="flex flex-wrap gap-1 md:flex-col">
          {roster.map((agent) => (
            <Item key={agent.id} to={`/classic/agents/${agent.id}`}>
              {agent.tag}
            </Item>
          ))}
        </ul>
        {sources.isPending && (
          <p className="px-3 text-xs text-muted-foreground">Loading the connectors…</p>
        )}
        {sources.isError && (
          <p className="px-3 text-xs text-bad">The connectors could not be listed.</p>
        )}
      </nav>
      <div className="min-w-0 flex-1">
        <Outlet />
      </div>
    </div>
  );
}
