/**
 * Links that stay in the view the reader is in (spec §8.1): the same panel links to a brief as
 * `/classic/briefs/<id>` in Classic view and as `/brief/<id>` over the office.
 */

import { useLocation } from 'react-router';

import { addressOf, viewOf, type Address, type ViewName } from '@/domain/views';

export interface ViewLinks {
  view: ViewName;
  home: () => Address;
  inbox: () => Address;
  brief: (briefId: string) => Address;
  agent: (agentId: string) => Address;
}

export function useViewLinks(): ViewLinks {
  const { pathname, search } = useLocation();
  const view = viewOf(pathname) ?? 'classic';
  return {
    view,
    home: () => addressOf(view, { kind: 'home' }, search),
    inbox: () => addressOf(view, { kind: 'inbox' }, search),
    brief: (briefId) => addressOf(view, { kind: 'brief', briefId }, search),
    agent: (agentId) => addressOf(view, { kind: 'agent', agentId }, search),
  };
}
