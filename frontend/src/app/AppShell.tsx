/** Every route's frame: a skip link, the HUD and the main landmark (spec §8.2, §10). */

import { Outlet } from 'react-router';

import { Hud } from '@/hud/Hud';

export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <Hud />
      <main id="main" tabIndex={-1} className="flex-1 p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  );
}
