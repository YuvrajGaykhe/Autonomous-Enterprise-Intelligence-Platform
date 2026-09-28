/**
 * Classic view's overview: the API's own health report, in the four states (§8.7), and the About
 * panel with the staff directory (§9.2, §10).
 */

import { useQuery } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router';

import { healthQuery } from '@/api/queries';
import { COPY } from '@/copy';
import { useRoster } from '@/data/useRoster';
import { NameTag } from '@/panels/chips';
import { QueryView } from '@/states/states';
import { Card, CardTitle } from '@/ui/card';

function AboutAgents() {
  const { roster } = useRoster();
  const { search } = useLocation();
  return (
    <Card aria-labelledby="about-agents" className="space-y-3">
      <CardTitle id="about-agents">About the agents</CardTitle>
      <p className="text-sm">{COPY.aboutAgents}</p>
      <ul className="grid gap-2 sm:grid-cols-2">
        {roster.map((agent) => (
          <li key={agent.id}>
            <Link
              to={{ pathname: `/classic/agents/${agent.id}`, search }}
              className="block space-y-1 rounded-lg border p-3 hover:bg-muted"
            >
              <NameTag tag={agent.tag} />
              <span className="block text-sm">{agent.role}</span>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function ClassicHome() {
  const query = useQuery(healthQuery());
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Overview</h1>
      <Card aria-labelledby="system-status">
        <CardTitle id="system-status">System status</CardTitle>
        <div className="mt-3">
          <QueryView query={query} label="system status">
            {({ data, requestId }) => (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted-foreground">Service</dt>
                <dd className="font-mono">{data.service}</dd>
                <dt className="text-muted-foreground">Version</dt>
                <dd className="font-mono">{data.version}</dd>
                <dt className="text-muted-foreground">Status</dt>
                <dd>{data.status}</dd>
                <dt className="text-muted-foreground">Database</dt>
                <dd>{data.checks.database}</dd>
                <dt className="text-muted-foreground">Request id</dt>
                <dd className="font-mono text-xs">{requestId ?? 'none received'}</dd>
              </dl>
            )}
          </QueryView>
        </div>
      </Card>
      <AboutAgents />
    </div>
  );
}
