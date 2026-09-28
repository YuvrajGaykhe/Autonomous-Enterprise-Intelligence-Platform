/**
 * Bands, the executive badge, decision status and name tags (spec §7.1, §9.3, §10). Each carries
 * a word and a glyph, so colour never carries meaning alone.
 */

import {
  Circle,
  CircleCheck,
  CircleX,
  Clock,
  Eye,
  OctagonAlert,
  Pin,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react';

import type { RiskBand } from '@/api/schemas/briefPayloadV1';
import type { BriefResponse } from '@/api/schemas/risk';
import { COPY } from '@/copy';
import { BANDS_HIGHEST_FIRST } from '@/domain/bands';
import { cn } from '@/lib/utils';

const chip =
  'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold whitespace-nowrap';

const BAND_STYLE: Record<RiskBand, { icon: LucideIcon; className: string; iconClass: string }> = {
  NONE: {
    icon: Circle,
    className: 'border-band-none bg-band-none/10',
    iconClass: 'text-band-none',
  },
  WATCH: {
    icon: Eye,
    className: 'border-band-watch bg-band-watch/20',
    iconClass: 'text-foreground',
  },
  ELEVATED: {
    icon: TriangleAlert,
    className: 'border-band-elevated bg-band-elevated/15',
    iconClass: 'text-band-elevated',
  },
  CRITICAL: {
    icon: OctagonAlert,
    className: 'border-band-critical bg-band-critical/15',
    iconClass: 'text-band-critical',
  },
};

export function BandChip({ band }: { band: RiskBand }) {
  const style = BAND_STYLE[band];
  const Icon = style.icon;
  return (
    <span className={cn(chip, style.className)} data-band={band}>
      <Icon aria-hidden="true" className={cn('size-3.5', style.iconClass)} />
      {band}
    </span>
  );
}

export function ExecutiveBadge() {
  return (
    <span className={cn(chip, 'border-primary bg-primary text-primary-foreground')}>
      <Pin aria-hidden="true" className="size-3.5" />
      EXECUTIVE
    </span>
  );
}

const STATUS_STYLE: Record<
  BriefResponse['decision_status'],
  { icon: LucideIcon; className: string }
> = {
  PENDING: { icon: Clock, className: 'border-bulb-waiting bg-bulb-waiting/15' },
  APPROVED: { icon: CircleCheck, className: 'border-ok bg-ok/10' },
  REJECTED: { icon: CircleX, className: 'border-bad bg-bad/10' },
};

export function DecisionStatusChip({ status }: { status: BriefResponse['decision_status'] }) {
  const style = STATUS_STYLE[status];
  const Icon = style.icon;
  return (
    <span className={cn(chip, style.className)} data-decision-status={status}>
      <Icon aria-hidden="true" className="size-3.5" />
      {status}
    </span>
  );
}

/** An agent's name tag: a black pill with white monospace capitals (§9.3). */
export function NameTag({ tag }: { tag: string }) {
  return (
    <span className="inline-block rounded-full bg-black px-2.5 py-0.5 font-mono text-xs font-medium tracking-wide text-white uppercase ring-1 ring-white/25">
      {tag}
    </span>
  );
}

/** The four bands with their glyphs, and the fixed line that a band is not a probability. */
export function BandLegend() {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span className="sr-only">Bands, highest first:</span>
      {BANDS_HIGHEST_FIRST.map((band) => (
        <BandChip key={band} band={band} />
      ))}
      <span>{COPY.bandLegend}</span>
    </div>
  );
}
