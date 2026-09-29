/** Classic view's CEO inbox (spec §7.2, §8.1). */

import { FIXED_AGENTS } from '@/domain/roster';
import { CeoInbox } from '@/panels/CeoInbox';

const CEO = FIXED_AGENTS.find((agent) => agent.kind === 'ceo');

export function ClassicInbox() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">CEO inbox</h1>
      {CEO !== undefined && <p className="text-sm">{CEO.role}</p>}
      <CeoInbox />
    </div>
  );
}
