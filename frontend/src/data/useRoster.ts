/**
 * The roster (spec §9.2): the fixed VS-01 agents at once, and one connector per configured source
 * once `GET /sources` answers.
 */

import { useQuery } from '@tanstack/react-query';

import { sourcesQuery } from '@/api/queries';
import { FIXED_AGENTS, rosterFor } from '@/domain/roster';

export function useRoster() {
  const sources = useQuery(sourcesQuery());
  const roster = sources.data === undefined ? [...FIXED_AGENTS] : rosterFor(sources.data.data);
  return { roster, sources };
}
