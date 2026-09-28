/**
 * The top bar (spec §8.2). F1 carries the product name, the health light and the `as_of`
 * selector; Run assessment, the view, pixel and sound toggles, Replay and the tour arrive
 * with the phases that build what they control (§14).
 */

import { Link, useLocation } from 'react-router';

import { COPY } from '@/copy';

import { AsOfSelector } from './AsOfSelector';
import { HealthLight } from './HealthLight';

export function Hud() {
  const { search } = useLocation();
  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b bg-card px-4 py-2">
      <Link to={{ pathname: '/classic', search }} className="text-lg font-semibold tracking-tight">
        {COPY.productName}
      </Link>
      <HealthLight />
      <div className="ml-auto">
        <AsOfSelector />
      </div>
    </header>
  );
}
