/**
 * The HUD's view switches (spec §8.2): Office or Classic (D-F-6), and, in the office, Pixel or
 * Smooth (D-F-5) and Sound (off by default, D-F-19). Each choice is remembered in this browser
 * (§11). The view switch goes to the twin of the current address, so the open panel or brief
 * stays open. A window too narrow for the office offers Classic only (F6).
 */

import { Volume2, VolumeX } from 'lucide-react';
import { Link, useLocation, useSearchParams } from 'react-router';

import { OFFICE_PARAMS, pixelArt, twinAddress, viewOf, type ViewName } from '@/domain/views';
import { STORAGE_KEYS, writeStored } from '@/lib/storage';
import { cn } from '@/lib/utils';
import { OFFICE_MIN_WIDTH, useNarrowWindow } from '@/lib/viewport';
import { usePreferences } from '@/state/preferences';

const segment =
  'rounded px-2.5 py-0.5 text-sm font-medium hover:bg-muted aria-[current=page]:bg-primary aria-[current=page]:text-primary-foreground aria-pressed:bg-primary aria-pressed:text-primary-foreground';

export function ViewSwitch() {
  const { pathname, search } = useLocation();
  const current = viewOf(pathname);
  const narrow = useNarrowWindow();
  const item = (view: ViewName, label: string) =>
    view === 'office' && narrow ? (
      <span
        aria-disabled="true"
        title={`The office needs a window at least ${OFFICE_MIN_WIDTH} pixels wide`}
        className={cn(segment, 'cursor-not-allowed text-muted-foreground hover:bg-transparent')}
      >
        {label}
        <span className="sr-only"> (needs a wider window)</span>
      </span>
    ) : (
      <Link
        to={current === view ? { pathname, search } : twinAddress(view, pathname, search)}
        aria-current={current === view ? 'page' : undefined}
        onClick={() => writeStored(STORAGE_KEYS.view, view)}
        className={segment}
      >
        {label}
      </Link>
    );
  return (
    <nav aria-label="View" className="flex rounded-md border bg-card p-0.5">
      {item('office', 'Office')}
      {item('classic', 'Classic')}
    </nav>
  );
}

export function PixelSwitch() {
  const [params, setParams] = useSearchParams();
  const stored = usePreferences((state) => state.pixel);
  const setPixel = usePreferences((state) => state.setPixel);
  const pixel = pixelArt(params.get(OFFICE_PARAMS.pixel), stored ? '1' : '0');
  const choose = (next: boolean) => {
    setPixel(next);
    if (params.has(OFFICE_PARAMS.pixel)) {
      setParams(
        (currentParams) => {
          const updated = new URLSearchParams(currentParams);
          updated.delete(OFFICE_PARAMS.pixel);
          return updated;
        },
        { replace: true },
      );
    }
  };
  return (
    <div role="group" aria-label="Rendering" className="flex rounded-md border bg-card p-0.5">
      <button
        type="button"
        aria-pressed={pixel}
        onClick={() => choose(true)}
        className={cn(segment)}
      >
        Pixel
      </button>
      <button
        type="button"
        aria-pressed={!pixel}
        onClick={() => choose(false)}
        className={cn(segment)}
      >
        Smooth
      </button>
    </div>
  );
}

export function SoundSwitch() {
  const sound = usePreferences((state) => state.sound);
  const setSound = usePreferences((state) => state.setSound);
  return (
    <button
      type="button"
      aria-pressed={sound}
      onClick={() => setSound(!sound)}
      className={cn(segment, 'flex items-center gap-1.5 rounded-md border bg-card py-1')}
    >
      {sound ? (
        <Volume2 aria-hidden="true" className="size-4" />
      ) : (
        <VolumeX aria-hidden="true" className="size-4" />
      )}
      Sound
    </button>
  );
}
