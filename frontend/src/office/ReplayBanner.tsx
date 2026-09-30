/**
 * The replay banner (spec §9.6, Appendix A): present for the whole of a replay, so nobody takes a
 * replay for new work. Dismissing it ends the replay, and the agents go back to the Break Area.
 */

import { History, X } from 'lucide-react';

import { useDirector } from '@/state/director';
import { Button } from '@/ui/button';

export function ReplayBanner({ banner }: { banner: string | null }) {
  const end = useDirector((state) => state.end);
  if (banner === null) return null;
  return (
    <div
      role="status"
      aria-label="Replay"
      className="absolute top-3 left-1/2 z-30 flex max-w-xl -translate-x-1/2 items-center gap-2 rounded-full border-2 border-[#22d3ee] bg-[#0b1d26]/95 py-1 pr-1 pl-3 text-[#e6fbff] shadow-lg"
    >
      <History aria-hidden="true" className="size-4 shrink-0 text-[#22d3ee]" />
      <span className="font-pixel text-xs">{banner}</span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => end()}
        aria-label="End the replay"
        className="h-7 rounded-full px-2 text-[#e6fbff] hover:bg-white/15"
      >
        <X aria-hidden="true" />
      </Button>
    </div>
  );
}
