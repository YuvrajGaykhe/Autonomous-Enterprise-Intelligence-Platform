/**
 * The top bar (spec §8.2): the product name, the health light, the Office/Classic switch, and in
 * the office the Pixel/Smooth switch, Sound and Replay (F4); the `as_of` selector and Run
 * assessment. The tour arrives with F6 (§14).
 */

import { Link } from 'react-router';

import { useViewLinks } from '@/app/links';
import { COPY } from '@/copy';

import { AsOfSelector } from './AsOfSelector';
import { HealthLight } from './HealthLight';
import { ReplayButton } from './ReplayButton';
import { RunAssessmentButton } from './RunAssessmentControls';
import { PixelSwitch, SoundSwitch, ViewSwitch } from './ViewToggles';

export function Hud() {
  const links = useViewLinks();
  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b bg-card px-4 py-2">
      <Link to={links.home()} className="text-lg font-semibold tracking-tight">
        {COPY.productName}
      </Link>
      <HealthLight />
      <div className="ml-auto flex flex-wrap items-center gap-3">
        <ViewSwitch />
        {links.view === 'office' && <PixelSwitch />}
        {links.view === 'office' && <SoundSwitch />}
        <AsOfSelector />
        {links.view === 'office' && <ReplayButton />}
        <RunAssessmentButton />
      </div>
    </header>
  );
}
