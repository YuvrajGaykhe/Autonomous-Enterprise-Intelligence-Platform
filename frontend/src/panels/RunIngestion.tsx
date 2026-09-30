/**
 * Run ingestion (spec R-F-6, §7.6, §9.5, R-F-7): the third and last write. It sends
 * `{"source": …}` only, and is enabled only while that source's health check says healthy. An
 * unchanged source yields a `NOOP` run, and the result says so.
 *
 * A refusal (422) created no run. A 500 may have left a FAILED run (DERIVED,
 * `app/api/v1/ingestion.py`), and a request with no answer has an unknown outcome: in both cases the
 * page counts the runs again before it offers a retry. No POST is retried automatically.
 *
 * In the office it is also a show: the connector works while the POST is in flight, then carries
 * the run's own outcome to MEMORY under the replay banner.
 */

import { useQueryClient } from '@tanstack/react-query';
import { Download, RotateCw } from 'lucide-react';
import { useState } from 'react';
import { useLocation } from 'react-router';

import { ApiError } from '@/api/client';
import { countRuns, startIngestion } from '@/api/ingestion';
import { invalidateAfterIngestion } from '@/api/queries';
import type { IngestionRunCreatedResponse } from '@/api/schemas/operations';
import { COPY, fill } from '@/copy';
import { startHold, startLive, startReplay } from '@/data/shows';
import { useRoster } from '@/data/useRoster';
import { ingestionEpisode } from '@/domain/episodes';
import { officeLayout } from '@/domain/layout';
import { classifyWriteFailure, failureRequestId, type WriteFailure } from '@/domain/outcomes';
import { viewOf } from '@/domain/views';
import { useDirector } from '@/state/director';
import { ErrorState } from '@/states/states';
import { Button } from '@/ui/button';

type Phase =
  | { kind: 'idle' }
  | { kind: 'running' }
  /** The count before the POST failed, so nothing was sent. */
  | { kind: 'not-sent'; error: unknown }
  | { kind: 'done'; run: IngestionRunCreatedResponse }
  /** The API refused the request: no run was created. */
  | { kind: 'refused'; failure: WriteFailure }
  | { kind: 'checking' }
  | { kind: 'checked'; landed: boolean }
  | { kind: 'check-failed'; error: unknown; before: number };

const mono = 'font-mono text-xs';

/** The outcomes that need attention; the others are reported politely. */
const ALERTS = new Set<Phase['kind']>(['not-sent', 'refused', 'check-failed']);

function Outcome({ run }: { run: IngestionRunCreatedResponse }) {
  return (
    <div className="space-y-2">
      <p>
        Run <span className={mono}>{run.run_id.slice(0, 8)}</span> finished{' '}
        <strong>{run.status}</strong>: {run.records_fetched} fetched, {run.records_inserted} new,{' '}
        {run.records_updated} updated, {run.records_unchanged} unchanged
        {run.status === 'NOOP' ? ', so nothing changed.' : '.'}
      </p>
      {run.entities.length > 0 && (
        <table className="w-full text-left text-xs">
          <caption className="sr-only">Per entity</caption>
          <thead>
            <tr className="text-muted-foreground">
              <th scope="col">Entity</th>
              <th scope="col">Status</th>
              <th scope="col">New</th>
              <th scope="col">Updated</th>
              <th scope="col">Unchanged</th>
              <th scope="col">Rejected</th>
              <th scope="col">Failed</th>
            </tr>
          </thead>
          <tbody>
            {run.entities.map((entity) => (
              <tr key={entity.entity_type}>
                <th scope="row" className={mono}>
                  {entity.entity_type}
                </th>
                <td>{entity.status}</td>
                <td>{entity.records_inserted}</td>
                <td>{entity.records_updated}</td>
                <td>{entity.records_unchanged}</td>
                <td>{entity.records_rejected}</td>
                <td>{entity.records_failed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function RunIngestion({ source, healthy }: { source: string; healthy: boolean }) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const client = useQueryClient();
  const { roster } = useRoster();
  const { pathname } = useLocation();
  const inOffice = viewOf(pathname) === 'office';
  const busy = phase.kind === 'running' || phase.kind === 'checking';

  async function recount(before: number) {
    setPhase({ kind: 'checking' });
    try {
      const after = await countRuns();
      const landed = after.total > before;
      setPhase({ kind: 'checked', landed });
      if (landed) await invalidateAfterIngestion(client);
    } catch (error) {
      setPhase({ kind: 'check-failed', error, before });
    }
  }

  async function run() {
    setPhase({ kind: 'running' });
    let before: number;
    try {
      before = (await countRuns()).total;
    } catch (error) {
      setPhase({ kind: 'not-sent', error });
      return;
    }
    const live = inOffice ? startLive('ingestion', [source]) : null;
    let created: IngestionRunCreatedResponse;
    try {
      created = (await startIngestion(source)).data;
    } catch (error) {
      if (live !== null) useDirector.getState().end(live);
      const failure = classifyWriteFailure(error);
      // A 500 may have left a FAILED run: like no answer at all, it is re-read first.
      const mayHaveRun =
        failure.kind === 'unknown' || (error instanceof ApiError && error.status >= 500);
      if (mayHaveRun) await recount(before);
      else setPhase({ kind: 'refused', failure });
      return;
    }
    const hold = live === null ? null : startHold('ingestion', [source]);
    setPhase({ kind: 'done', run: created });
    await invalidateAfterIngestion(client);
    if (hold === null || useDirector.getState().show?.id !== hold) return;
    // MEMORY was not in the live show, so the replay gives everyone the full walk to their desks.
    const played = startReplay(
      'ingestion',
      ingestionEpisode(source, created),
      officeLayout(roster),
      fill(COPY.replayBanner, { date: created.started_at.slice(0, 10) }),
    );
    if (played === null) useDirector.getState().end(hold);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={() => void run()} disabled={!healthy || busy}>
          <Download aria-hidden="true" />
          {phase.kind === 'running' ? 'Ingesting…' : 'Run ingestion'}
        </Button>
        {!healthy && (
          <p className="text-xs text-muted-foreground">
            Enabled only while this source&apos;s health check says healthy.
          </p>
        )}
      </div>
      {phase.kind !== 'idle' && phase.kind !== 'running' && (
        <div
          role={ALERTS.has(phase.kind) ? 'alert' : 'status'}
          aria-label="Ingestion run"
          className="text-sm"
        >
          {phase.kind === 'done' && <Outcome run={phase.run} />}
          {phase.kind === 'not-sent' && (
            <div className="space-y-2">
              <p>The ingestion was not sent, because the API could not be read first.</p>
              <ErrorState error={phase.error} />
            </div>
          )}
          {phase.kind === 'refused' && (
            <div className="space-y-2">
              <p>The API refused the ingestion. No run was created.</p>
              <ErrorState error={phase.failure.error} />
              <p className={mono}>request {failureRequestId(phase.failure) ?? 'none'}</p>
            </div>
          )}
          {phase.kind === 'checking' && <p>{COPY.unknownOutcome}</p>}
          {phase.kind === 'checked' &&
            (phase.landed ? (
              <p>The ingestion was recorded: its run is listed below.</p>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <p>No new run was recorded, so running it again is safe.</p>
                <Button variant="outline" size="sm" onClick={() => void run()} disabled={!healthy}>
                  <RotateCw aria-hidden="true" />
                  Retry
                </Button>
              </div>
            ))}
          {phase.kind === 'check-failed' && (
            <div className="space-y-2">
              <p>The check could not reach the API, so the result is still unknown.</p>
              <ErrorState error={phase.error} />
              <Button variant="outline" size="sm" onClick={() => void recount(phase.before)}>
                <RotateCw aria-hidden="true" />
                Check again
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
