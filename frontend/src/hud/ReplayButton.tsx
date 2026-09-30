/**
 * The HUD's Replay (spec §8.2, §9.5, §9.6): replays the shown snapshot's recorded results, under
 * the replay banner. Nothing replays on its own; a finished run replays its own results. It waits
 * while a run is in flight.
 */

import { useQueryClient } from '@tanstack/react-query';
import { History } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { COPY, fill } from '@/copy';
import { loadAssessmentEpisode, startReplay } from '@/data/shows';
import { useInbox, useSnapshotParam } from '@/data/useInbox';
import { useRoster } from '@/data/useRoster';
import { officeLayout } from '@/domain/layout';
import { useDirector } from '@/state/director';
import { useSession } from '@/state/session';
import { Button } from '@/ui/button';

import { useAsOf } from './useAsOf';

export function ReplayButton() {
  const [asOf] = useAsOf();
  const [snapshotParam] = useSnapshotParam();
  const inbox = useInbox(asOf, snapshotParam);
  const lastRun = useSession((state) => state.lastRun);
  const client = useQueryClient();
  const { roster } = useRoster();
  const show = useDirector((state) => state.show);
  const [loading, setLoading] = useState(false);
  // A replay whose data arrives after the HUD has gone (another page) is not started.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const ready = inbox.status === 'ready' && inbox.snapshot !== null;
  const running = show !== null && show.kind !== 'replay';

  async function replay() {
    if (inbox.status !== 'ready') return;
    const date = inbox.asOf;
    setLoading(true);
    try {
      const episode = await loadAssessmentEpisode(client, {
        asOf: date,
        fingerprintParam: snapshotParam,
        runAssessmentIds: lastRun?.asOf === date ? lastRun.assessmentIds : [],
      });
      if (mounted.current)
        startReplay('assessment', episode, officeLayout(roster), fill(COPY.replayBanner, { date }));
    } catch {
      // The inbox shows why its data cannot be read; there is nothing to replay.
    } finally {
      if (mounted.current) setLoading(false);
    }
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => void replay()}
      disabled={!ready || running || loading}
      title="Replay the shown snapshot's recorded results"
    >
      <History aria-hidden="true" />
      Replay
    </Button>
  );
}
