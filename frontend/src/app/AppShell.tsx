/**
 * Every route's frame: a skip link, the HUD, the outcome of the latest assessment run and the main
 * landmark (spec §8.2, §10). The office fills the window below the HUD; Classic pages scroll.
 *
 * A reader who arrives at either view's home is shown the tour, once per browser (F6). A reader
 * who arrives on a deep link is not interrupted; the HUD's Tour opens it.
 */

import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router';

import { classicTarget, officeTarget, viewOf } from '@/domain/views';
import { Hud } from '@/hud/Hud';
import { Tour } from '@/hud/Tour';
import { useTour } from '@/state/tour';
import { cn } from '@/lib/utils';
import { RunStatus } from '@/hud/RunAssessmentControls';
import { RunAssessmentProvider } from '@/hud/runAssessment';

export function AppShell() {
  const { pathname, search } = useLocation();
  const office = viewOf(pathname) === 'office';
  const arrive = useTour((state) => state.arrive);
  // Only the first address counts: the arrival, not every later page.
  const [arrivedHome] = useState(
    () => (officeTarget(pathname, search) ?? classicTarget(pathname))?.kind === 'home',
  );
  useEffect(() => {
    if (arrivedHome) arrive();
  }, [arrivedHome, arrive]);
  return (
    <RunAssessmentProvider>
      <div className={cn('flex flex-col', office ? 'h-dvh overflow-hidden' : 'min-h-screen')}>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <Hud />
        <RunStatus />
        <Tour />
        <main
          id="main"
          tabIndex={-1}
          className={cn('flex-1', office ? 'relative min-h-0' : 'p-4 md:p-6')}
        >
          <Outlet />
        </main>
      </div>
    </RunAssessmentProvider>
  );
}
