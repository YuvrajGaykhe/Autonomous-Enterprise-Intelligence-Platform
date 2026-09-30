/**
 * Starting the office's shows (spec §9.5, §9.6, D-F-1): a live run while a POST is in flight, a
 * hold while its replay's data is read, and the replay itself, built only from API responses.
 *
 * The replay of an assessment reads the list at its date, the snapshot's briefs and the featured
 * brief through TanStack Query, so the inbox's own cached requests are reused (§6.7).
 */

import type { QueryClient } from '@tanstack/react-query';

import { assessmentsQuery, briefQuery } from '@/api/queries';
import { BEATS, holdTimeline, liveTimeline, replayTimeline, type Layout } from '@/domain/director';
import { assessmentEpisode, participants, type Episode } from '@/domain/episodes';
import { chooseSnapshot, groupSnapshots, inboxRows, snapshotBriefIds } from '@/domain/inbox';
import { gatherSeconds } from '@/domain/layout';
import { FIXED_AGENTS } from '@/domain/roster';
import { directorClock, useDirector, type Show } from '@/state/director';

/** An assessment's agents with bodies, in the code's stage order (DERIVED, `assessment.py`). */
export const ASSESSMENT_CAST = FIXED_AGENTS.filter((agent) => agent.kind !== 'ceo').map(
  (agent) => agent.id,
);

/** The only caption a live run shows: no other value exists until the POST answers (§9.6). */
export const LIVE_CAPTIONS: Readonly<Record<Show['subject'], string>> = {
  assessment: 'ASSESSING…',
  ingestion: 'INGESTING…',
};

export interface SnapshotChoice {
  asOf: string;
  /** The `snapshot` URL parameter, when one is set. */
  fingerprintParam: string | null;
  /** The assessment ids this session's run returned, to find its snapshot. */
  runAssessmentIds: readonly string[];
}

/** The assessment episode of the snapshot the inbox would show for `choice` (§7.2, §9.5). */
export async function loadAssessmentEpisode(
  client: QueryClient,
  choice: SnapshotChoice,
): Promise<Episode> {
  const list = (await client.fetchQuery(assessmentsQuery(choice.asOf))).data;
  const snapshot = chooseSnapshot(groupSnapshots(list), {
    fingerprintParam: choice.fingerprintParam,
    runAssessmentIds: choice.runAssessmentIds,
  });
  if (snapshot === null) return { kind: 'assessment', steps: [] };
  const briefs = await Promise.all(
    snapshotBriefIds(snapshot).map((id) => client.fetchQuery(briefQuery(id))),
  );
  const responses = new Map(briefs.map(({ data }) => [data.response.id, data.response]));
  const rows = inboxRows(snapshot, responses, new Map());
  const first = rows[0];
  const featured = briefs.find(({ data }) => data.response.id === first?.briefId)?.data;
  return assessmentEpisode({
    asOf: choice.asOf,
    list,
    snapshot,
    rows,
    featured:
      featured?.supported === true
        ? { briefId: featured.response.id, payload: featured.payload }
        : null,
  });
}

export function startLive(subject: Show['subject'], cast: readonly string[]): number {
  return useDirector.getState().begin({
    kind: 'live',
    subject,
    timeline: liveTimeline(cast, LIVE_CAPTIONS[subject]),
    banner: null,
  });
}

export function startHold(subject: Show['subject'], cast: readonly string[]): number {
  return useDirector
    .getState()
    .begin({ kind: 'hold', subject, timeline: holdTimeline(cast), banner: null });
}

/** How long the show with `id` has been playing, in seconds; 0 if another plays now. */
export function playedFor(id: number): number {
  const show = useDirector.getState().show;
  return show === null || show.id !== id ? 0 : (directorClock.now() - show.startedAt) / 1000;
}

/**
 * Play `episode` under `banner`. Its agents first walk to their desks: a full walk from the Break
 * Area, less whatever a live run already gave them. Returns null for an episode with no step.
 */
export function startReplay(
  subject: Show['subject'],
  episode: Episode,
  layout: Layout,
  banner: string,
  alreadyWalked = 0,
): number | null {
  if (episode.steps.length === 0) return null;
  const gather = Math.max(
    BEATS.minimumGather,
    gatherSeconds(layout, participants(episode)) - alreadyWalked,
  );
  return useDirector.getState().begin({
    kind: 'replay',
    subject,
    timeline: replayTimeline(episode, layout, gather),
    banner,
  });
}
