/** The HUD's Run assessment button and the line that reports its outcome (spec §8.2, §7.6). */

import { Play, RotateCw, X } from 'lucide-react';
import { Link } from 'react-router';

import { useViewLinks } from '@/app/links';
import { COPY } from '@/copy';
import { failureRequestId, OUTCOME_MESSAGES } from '@/domain/outcomes';
import type { AsOf } from '@/domain/asOf';
import { ErrorState } from '@/states/states';
import { Button } from '@/ui/button';

import { isBusy, useRunAssessment, type RunPhase } from './runAssessment';
import { useAsOf } from './useAsOf';

export function RunAssessmentButton({ label = 'Run assessment' }: { label?: string }) {
  const [asOf] = useAsOf();
  const { phase, run } = useRunAssessment();
  return (
    <Button size="sm" onClick={() => void run(asOf)} disabled={isBusy(phase)}>
      <Play aria-hidden="true" />
      {phase.kind === 'running' ? 'Assessing…' : label}
    </Button>
  );
}

function dateOf(asOf: AsOf): string {
  return asOf.kind === 'date' ? asOf.date : "the latest ticket's date (Auto)";
}

function RetryButton({ asOf, label = 'Retry' }: { asOf: AsOf; label?: string }) {
  const { run } = useRunAssessment();
  return (
    <Button variant="outline" size="sm" onClick={() => void run(asOf)}>
      <RotateCw aria-hidden="true" />
      {label}
    </Button>
  );
}

function RequestId({ id }: { id: string | null }) {
  return <span className="font-mono text-xs text-muted-foreground">request {id ?? 'none'}</span>;
}

function Message({ phase }: { phase: Exclude<RunPhase, { kind: 'idle' }> }) {
  const { checkAgain } = useRunAssessment();
  const links = useViewLinks();
  switch (phase.kind) {
    case 'running':
      return <p>Assessing every customer at {dateOf(phase.asOf)}…</p>;
    case 'not-sent':
      return (
        <div className="space-y-2">
          <p>The assessment was not sent, because the API could not be read first.</p>
          <ErrorState error={phase.error} />
          <RetryButton asOf={phase.asOf} />
        </div>
      );
    case 'done':
      return phase.status === 201 ? (
        <p>
          Assessed {phase.assessed} customers at {phase.resolvedAsOf ?? 'the resolved date'}:{' '}
          {phase.briefs} briefs, {phase.created} new results.
        </p>
      ) : (
        <p>
          Already assessed at {phase.resolvedAsOf ?? 'the resolved date'}: all {phase.assessed}{' '}
          results existed, so nothing was written.
        </p>
      );
    case 'failed': {
      const { failure } = phase;
      if (failure.kind === 'scope-unresolved') return <p>{OUTCOME_MESSAGES.scopeUnresolved}</p>;
      if (failure.kind === 'invalid') {
        return (
          <div>
            <p>{OUTCOME_MESSAGES.invalid}</p>
            <ul className="list-disc pl-5 font-mono text-xs">
              {failure.fields.map((field) => (
                <li key={field}>{field}</li>
              ))}
            </ul>
          </div>
        );
      }
      if (failure.kind === 'unreadable' || failure.kind === 'unknown') {
        return <ErrorState error={failure.error} />;
      }
      return (
        <div className="flex flex-wrap items-center gap-3">
          <p>{OUTCOME_MESSAGES.nothingWritten}</p>
          <RequestId id={failureRequestId(failure)} />
          <RetryButton asOf={phase.asOf} />
        </div>
      );
    }
    case 'checking':
      return <p>{COPY.unknownOutcome}</p>;
    case 'checked':
      return phase.landed ? (
        <p>
          The assessment was recorded.{' '}
          <Link className="underline" to={links.inbox()}>
            Show the inbox
          </Link>
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <p>Nothing new was recorded, so running it again is safe.</p>
          <RetryButton asOf={phase.asOf} />
        </div>
      );
    case 'check-failed':
      return (
        <div className="space-y-2">
          <p>The check could not reach the API, so the result is still unknown.</p>
          <ErrorState error={phase.error} />
          <Button variant="outline" size="sm" onClick={() => void checkAgain()}>
            <RotateCw aria-hidden="true" />
            Check again
          </Button>
        </div>
      );
  }
}

const ALERTS = new Set(['not-sent', 'failed', 'check-failed']);

/** The outcome of this session's latest run, under the top bar. */
export function RunStatus() {
  const { phase, dismiss } = useRunAssessment();
  if (phase.kind === 'idle') return null;
  const alert = ALERTS.has(phase.kind);
  return (
    <div
      role={alert ? 'alert' : 'status'}
      aria-label="Assessment run"
      className="flex items-start gap-3 border-b bg-muted/60 px-4 py-2 text-sm"
    >
      <div className="min-w-0 flex-1">
        <Message phase={phase} />
      </div>
      {!isBusy(phase) && (
        <Button variant="ghost" size="sm" onClick={dismiss} aria-label="Dismiss">
          <X aria-hidden="true" />
        </Button>
      )}
    </div>
  );
}
