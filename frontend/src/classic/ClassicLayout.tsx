/**
 * Classic view: the same data as the office, as plain pages (D-F-6, spec §8.1). Its navigation is
 * also the staff directory: every agent, reachable by keyboard (§10). When the office could not
 * start, the WebGL notice says why the reader is here (§9.11); when the window is too narrow for
 * the office, a notice says so (F6).
 */

import { MonitorSmartphone, MonitorX } from 'lucide-react';
import { NavLink, Outlet, useLocation } from 'react-router';

import { COPY } from '@/copy';
import { useRoster } from '@/data/useRoster';
import { cn } from '@/lib/utils';
import { OFFICE_MIN_WIDTH, useNarrowWindow } from '@/lib/viewport';
import { useSession } from '@/state/session';
import { useTourSpot } from '@/state/tour';

const notice =
  'flex items-center gap-2 rounded-lg border border-band-watch bg-band-watch/15 px-3 py-2 text-sm';

function Item({
  to,
  end = false,
  spot,
  children,
}: {
  to: string;
  end?: boolean;
  spot?: 'on' | undefined;
  children: string;
}) {
  const { search } = useLocation();
  return (
    <li data-tour-spot={spot} className={spot === 'on' ? 'rounded-md bg-card' : undefined}>
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
  const webglFailed = useSession((state) => state.webglFailed);
  const narrow = useNarrowWindow();
  const agentsSpot = useTourSpot('agents');
  const inboxSpot = useTourSpot('inbox');
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      {webglFailed && (
        <p role="status" className={notice}>
          <MonitorX aria-hidden="true" className="size-4 shrink-0" />
          {COPY.webglFallback}
        </p>
      )}
      {narrow && !webglFailed && (
        <p role="status" className={notice}>
          <MonitorSmartphone aria-hidden="true" className="size-4 shrink-0" />
          {`The 3D office needs a window at least ${OFFICE_MIN_WIDTH} pixels wide, so this is Classic view. Every panel works the same.`}
        </p>
      )}
      <div className="flex flex-col gap-4 md:flex-row">
        <nav aria-label="Classic view" className="md:w-52 md:shrink-0">
          <ul className="flex flex-wrap gap-1 md:flex-col">
            <Item to="/classic" end>
              Overview
            </Item>
            <Item to="/classic/inbox" spot={inboxSpot}>
              CEO inbox
            </Item>
          </ul>
          <h2 className="mt-4 mb-1 px-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            Agents
          </h2>
          <ul
            aria-label="Staff directory"
            data-tour-spot={agentsSpot}
            className={cn(
              'flex flex-wrap gap-1 md:flex-col',
              agentsSpot === 'on' && 'rounded-md bg-card',
            )}
          >
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
    </div>
  );
}
