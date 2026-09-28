/**
 * The HUD's health light, from `GET /api/v1/health` (§8.2). The light always carries a word and a
 * glyph, never colour alone (§10).
 */

import { useQuery } from '@tanstack/react-query';
import { CircleAlert, CircleCheck, CircleDashed, RotateCw } from 'lucide-react';

import { describeFailure } from '@/api/failures';
import { healthQuery } from '@/api/queries';
import { Button } from '@/ui/button';

export function HealthLight() {
  const query = useQuery(healthQuery());

  if (query.isPending) {
    return (
      <p role="status" className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <CircleDashed aria-hidden="true" className="size-4" />
        API: checking…
      </p>
    );
  }

  if (query.isError) {
    const failure = describeFailure(query.error);
    return (
      <div role="alert" className="flex items-center gap-2 text-sm">
        <CircleAlert aria-hidden="true" className="size-4 text-bad" />
        <span className="font-medium text-bad">API unreachable</span>
        <span className="font-mono text-xs text-muted-foreground">
          {failure.code} · request {failure.requestId ?? 'none'}
        </span>
        <Button variant="ghost" size="sm" onClick={() => void query.refetch()}>
          <RotateCw aria-hidden="true" />
          Retry
        </Button>
      </div>
    );
  }

  const { data } = query.data;
  const healthy = data.status === 'healthy';
  const Glyph = healthy ? CircleCheck : CircleAlert;
  return (
    <p role="status" className="flex items-center gap-1.5 text-sm" data-testid="health-light">
      <Glyph aria-hidden="true" className={healthy ? 'size-4 text-ok' : 'size-4 text-bad'} />
      <span className="font-medium">API {data.status}</span>
      <span className="font-mono text-xs text-muted-foreground">
        database {data.checks.database} · v{data.version}
      </span>
    </p>
  );
}
