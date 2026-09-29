/**
 * Every route's frame: a skip link, the HUD, the outcome of the latest assessment run and the main
 * landmark (spec §8.2, §10). The office fills the window below the HUD; Classic pages scroll.
 */

import { Outlet, useLocation } from 'react-router';

import { viewOf } from '@/domain/views';
import { Hud } from '@/hud/Hud';
import { cn } from '@/lib/utils';
import { RunStatus } from '@/hud/RunAssessmentControls';
import { RunAssessmentProvider } from '@/hud/runAssessment';

export function AppShell() {
  const office = viewOf(useLocation().pathname) === 'office';
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
