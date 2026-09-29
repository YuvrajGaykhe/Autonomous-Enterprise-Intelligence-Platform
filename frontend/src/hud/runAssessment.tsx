/**
 * Run assessment (spec §6.6, §7.6, §8.2, D-F-14, R-F-7).
 *
 * The run's state lives in one provider, so the HUD's button and the inbox's empty-state button
 * are the same action. Before the POST, the page counts the assessments at the run's `as_of` (or
 * at every date, for Auto). A POST that never produced an answer has an unknown outcome: the page
 * counts again, and offers a retry only when nothing new was recorded. The POST is idempotent, so
 * that retry cannot write twice. No POST is retried automatically.
 */

import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router';

import { invalidateAfterAssessment } from '@/api/queries';
import { countAssessments, fetchAssessment, runAssessment } from '@/api/risk';
import { requestAsOf, type AsOf } from '@/domain/asOf';
import { classifyWriteFailure, type WriteFailure } from '@/domain/outcomes';
import { addressOf, viewOf } from '@/domain/views';
import { useSession } from '@/state/session';

export type RunPhase =
  | { kind: 'idle' }
  | { kind: 'running'; asOf: AsOf }
  /** The count before the POST failed, so nothing was sent. */
  | { kind: 'not-sent'; asOf: AsOf; error: unknown }
  | {
      kind: 'done';
      asOf: AsOf;
      status: number;
      resolvedAsOf: string | null;
      assessed: number;
      briefs: number;
      created: number;
    }
  | { kind: 'failed'; asOf: AsOf; failure: WriteFailure }
  | { kind: 'checking'; asOf: AsOf }
  | { kind: 'checked'; asOf: AsOf; landed: boolean }
  | { kind: 'check-failed'; asOf: AsOf; error: unknown; before: number };

interface RunContext {
  phase: RunPhase;
  run: (asOf: AsOf) => Promise<void>;
  checkAgain: () => Promise<void>;
  dismiss: () => void;
}

const Context = createContext<RunContext | null>(null);

export function useRunAssessment(): RunContext {
  const context = useContext(Context);
  if (context === null) throw new Error('useRunAssessment is used outside RunAssessmentProvider');
  return context;
}

export function RunAssessmentProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<RunPhase>({ kind: 'idle' });
  const client = useQueryClient();
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const setLastRun = useSession((state) => state.setLastRun);

  /** The run's snapshot, in the inbox of the view the reader is in (§7.2). */
  const showInbox = useCallback(() => {
    const params = new URLSearchParams(search);
    params.delete('snapshot');
    void navigate(addressOf(viewOf(pathname) ?? 'classic', { kind: 'inbox' }, params.toString()));
  }, [navigate, pathname, search]);

  const recount = useCallback(
    async (asOf: AsOf, before: number) => {
      setPhase({ kind: 'checking', asOf });
      try {
        const after = await countAssessments(requestAsOf(asOf));
        const landed = after.total > before;
        setPhase({ kind: 'checked', asOf, landed });
        if (landed) await invalidateAfterAssessment(client);
      } catch (error) {
        setPhase({ kind: 'check-failed', asOf, error, before });
      }
    },
    [client],
  );

  const run = useCallback(
    async (asOf: AsOf) => {
      setPhase({ kind: 'running', asOf });
      let before: number;
      try {
        before = (await countAssessments(requestAsOf(asOf))).total;
      } catch (error) {
        setPhase({ kind: 'not-sent', asOf, error });
        return;
      }
      let result: Awaited<ReturnType<typeof runAssessment>>;
      try {
        result = await runAssessment(requestAsOf(asOf));
      } catch (error) {
        const failure = classifyWriteFailure(error);
        if (failure.kind === 'unknown') await recount(asOf, before);
        else setPhase({ kind: 'failed', asOf, failure });
        return;
      }
      const items = result.data.items;
      let resolvedAsOf = asOf.kind === 'date' ? asOf.date : null;
      const [first] = items;
      if (resolvedAsOf === null && first !== undefined) {
        resolvedAsOf = await fetchAssessment(first.assessment_id).then(
          (detail) => detail.data.as_of,
          () => null,
        );
      }
      setLastRun({
        requested: asOf,
        asOf: resolvedAsOf,
        status: result.status,
        assessmentIds: items.map((item) => item.assessment_id),
        briefCount: items.filter((item) => item.brief_id !== null).length,
        createdCount: items.filter((item) => item.created).length,
      });
      await invalidateAfterAssessment(client);
      setPhase({
        kind: 'done',
        asOf,
        status: result.status,
        resolvedAsOf,
        assessed: items.length,
        briefs: items.filter((item) => item.brief_id !== null).length,
        created: items.filter((item) => item.created).length,
      });
      showInbox();
    },
    [client, recount, setLastRun, showInbox],
  );

  const checkAgain = useCallback(async () => {
    if (phase.kind === 'check-failed') await recount(phase.asOf, phase.before);
  }, [phase, recount]);

  const dismiss = useCallback(() => setPhase({ kind: 'idle' }), []);

  const value = useMemo(
    () => ({ phase, run, checkAgain, dismiss }),
    [phase, run, checkAgain, dismiss],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

/** Whether a run is in flight or being checked, so the button is disabled. */
export function isBusy(phase: RunPhase): boolean {
  return phase.kind === 'running' || phase.kind === 'checking';
}
