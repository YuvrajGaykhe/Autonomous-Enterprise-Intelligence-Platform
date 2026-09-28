/** Classic view's agent page (spec §8.1, §8.3): one agent's panel, found in the roster. */

import { useParams } from 'react-router';

import { useRoster } from '@/data/useRoster';
import { agentById } from '@/domain/roster';
import { AgentPanel } from '@/panels/AgentPanel';
import { ErrorState, LoadingState } from '@/states/states';

import { NotFound } from './NotFound';

export function ClassicAgent() {
  const { agentId = '' } = useParams();
  const { roster, sources } = useRoster();
  const agent = agentById(roster, agentId);
  if (agent !== null) return <AgentPanel agent={agent} />;
  if (sources.isPending) return <LoadingState label="the agent roster" />;
  if (sources.isError) {
    return <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />;
  }
  return <NotFound />;
}
