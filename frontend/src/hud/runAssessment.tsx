/**
 * Run assessment (spec §6.6, §7.6, §8.2, §9.6, D-F-14, R-F-7).
 *
 * The run's state lives in one provider, so the HUD's button and the inbox's empty-state button
 * are the same action. Before the POST, the page counts the assessments at the run's `as_of` (or
 * at every date, for Auto). A POST that never produced an answer has an unknown outcome: the page
 * counts again, and offers a retry only when nothing new was recorded. The POST is idempotent, so
 * that retry cannot write twice. No POST is retried automatically.
 *
 * In the office the run is also a show (F4): its agents work while the POST is in flight, wait at
 * their desks while the replay's data is read, then replay the recorded results under the banner,
 * "Already assessed" when the API answered 200. The office does not open the inbox over the
 * replay; the CEO's desk says what waits. Classic view opens the inbox, as before.
 */

import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router';

import { invalidateAfterAssessment } from '@/api/queries';
import { countAssessments, fetchAssessment, runAssessment } from '@/api/risk';
import { COPY, fill } from '@/copy';
import { useRoster } from '@/data/useRoster';
import { SNAPSHOT_PARAM } from '@/data/useInbox';
import {
  ASSESSMENT_CAST,
  loadAssessmentEpisode,
  playedFor,
  startHold,
  startLive,
  startReplay,
} from '@/data/shows';
import { requestAsOf, type AsOf } from '@/domain/asOf';
import { officeLayout } from '@/domain/layout';
import { classifyWriteFailure, type WriteFailure } from '@/domain/outcomes';
import { addressOf, viewOf } from '@/domain/views';
import { useDirector } from '@/state/director';
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
  const { roster } = useRoster();
  const inOffice = viewOf(pathname) === 'office';

  /**
   * The run's snapshot (§7.2): Classic opens its inbox; the office forgets any chosen snapshot,
   * so the tray and the replay show the run's.
   */
  const showInbox = useCallback(() => {
    const params = new URLSearchParams(search);
    params.delete(SNAPSHOT_PARAM);
    if (viewOf(pathname) === 'office') {
      if (new URLSearchParams(search).has(SNAPSHOT_PARAM))
        void navigate({ pathname, search: params.toString() }, { replace: true });
      return;
    }
    void navigate(addressOf('classic', { kind: 'inbox' }, params.toString()));
  }, [navigate, pathname, search]);

  /** Replay the run's recorded results (§9.6), or end the hold when there is nothing to play. */
  const replay = useCallback(
    async (hold: number, walked: number, status: number, date: string, ids: string[]) => {
      const end = () => useDirector.getState().end(hold);
      try {
        const episode = await loadAssessmentEpisode(client, {
          asOf: date,
          fingerprintParam: null,
          runAssessmentIds: ids,
        });
        if (useDirector.getState().show?.id !== hold) return;
        const banner =
          status === 200 ? COPY.alreadyAssessedBanner : fill(COPY.replayBanner, { date });
        if (startReplay('assessment', episode, officeLayout(roster), banner, walked) === null)
          end();
      } catch {
        // The run itself is reported by the status line; without its data there is no replay.
        end();
      }
    },
    [client, roster],
  );

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
      const live = inOffice ? startLive('assessment', ASSESSMENT_CAST) : null;
      let result: Awaited<ReturnType<typeof runAssessment>>;
      try {
        result = await runAssessment(requestAsOf(asOf));
      } catch (error) {
        if (live !== null) useDirector.getState().end(live);
        const failure = classifyWriteFailure(error);
        if (failure.kind === 'unknown') await recount(asOf, before);
        else setPhase({ kind: 'failed', asOf, failure });
        return;
      }
      const walked = live === null ? 0 : playedFor(live);
      const hold = live === null ? null : startHold('assessment', ASSESSMENT_CAST);
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
      if (hold === null) return;
      if (resolvedAsOf === null) useDirector.getState().end(hold);
      else
        await replay(
          hold,
          walked,
          result.status,
          resolvedAsOf,
          items.map((item) => item.assessment_id),
        );
    },
    [client, inOffice, recount, replay, setLastRun, showInbox],
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
