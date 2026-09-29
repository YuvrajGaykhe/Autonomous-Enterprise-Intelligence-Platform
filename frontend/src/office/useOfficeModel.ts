/**
 * The office's model (spec §9.2–§9.4, §8.7): each agent's state from the requests behind its
 * panel, SIGNALS_AGENT's board, the CEO's tray and corkboard. TanStack Query shares these requests
 * with the panels, so opening a panel reads what the office already loaded.
 */

import { useQueries, useQuery } from '@tanstack/react-query';

import { describeFailure } from '@/api/failures';
import {
  assessmentQuery,
  briefQuery,
  decisionsQuery,
  healthQuery,
  sourceHealthQuery,
} from '@/api/queries';
import { useInbox, useSnapshotParam } from '@/data/useInbox';
import { useRoster } from '@/data/useRoster';
import { useSelectedRow, type SelectedRowState } from '@/data/useSelectedRow';
import { combine, officeStatus, type Readiness } from '@/domain/agentLook';
import { signalRows } from '@/domain/briefView';
import { pendingCount } from '@/domain/inbox';
import { signalsBoard } from '@/domain/monitor';
import type { Agent } from '@/domain/roster';
import { useAsOf } from '@/hud/useAsOf';

import type { BoardState, CorkNote, WorldAgent } from './worldTypes';

interface QueryLike<T> {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  data: T | undefined;
}

function failureLine(error: unknown): string {
  const failure = describeFailure(error);
  return `${failure.message} (${failure.code})`;
}

/** A query as readiness; `problem` reads a failure the response itself reports. */
function fromQuery<T>(query: QueryLike<T>, problem?: (data: T) => string | null): Readiness {
  if (query.isError) return { kind: 'failed', reason: failureLine(query.error) };
  if (query.data === undefined) return { kind: 'loading' };
  const reason = problem?.(query.data) ?? null;
  return reason === null ? { kind: 'ready' } : { kind: 'failed', reason };
}

function selectionReadiness(selected: SelectedRowState): Readiness {
  if (selected.status === 'loading') return { kind: 'loading' };
  if (selected.status === 'error') return { kind: 'failed', reason: failureLine(selected.error) };
  return { kind: 'ready' };
}

export interface OfficeModel {
  agents: WorldAgent[];
  board: BoardState;
  trayCount: number | null;
  notes: CorkNote[];
}

export function useOfficeModel(): OfficeModel {
  const { roster } = useRoster();
  const [asOf] = useAsOf();
  const [snapshotParam] = useSnapshotParam();
  const inbox = useInbox(asOf, snapshotParam);
  const selected = useSelectedRow();
  const row = selected.status === 'ready' ? selected.row : null;

  const health = useQuery(healthQuery());
  const connectors = roster.filter((agent) => agent.kind === 'connector');
  const sourceHealth = useQueries({
    queries: connectors.map((agent) => sourceHealthQuery(agent.id)),
  });
  const brief = useQuery({ ...briefQuery(row?.briefId ?? ''), enabled: row !== null });
  const assessment = useQuery({
    ...assessmentQuery(row?.assessmentId ?? ''),
    enabled: row !== null,
  });
  const decisions = useQuery({ ...decisionsQuery(row?.briefId ?? ''), enabled: row !== null });

  const connectorStates = new Map(
    sourceHealth.map((query, index) => [
      connectors[index]?.id,
      fromQuery(query, ({ data }) =>
        data.status === 'unhealthy' ? 'Its source reports unhealthy.' : null,
      ),
    ]),
  );
  const selection = selectionReadiness(selected);
  const onSelection = (query: QueryLike<unknown>) =>
    row === null ? selection : combine(selection, fromQuery(query));

  const readiness = (agent: Agent): Readiness => {
    switch (agent.kind) {
      case 'connector':
        return connectorStates.get(agent.id) ?? { kind: 'loading' };
      case 'memory':
        return fromQuery(health, ({ data }) =>
          data.status === 'healthy'
            ? null
            : `The API reports ${data.status}, database ${data.checks.database}.`,
        );
      case 'linker':
      case 'reconciler':
      case 'briefWriter':
        return onSelection(brief);
      case 'signals':
      case 'sales':
      case 'support':
        return onSelection(assessment);
      case 'ceo':
        if (inbox.status === 'loading') return { kind: 'loading' };
        if (inbox.status === 'error') return { kind: 'failed', reason: failureLine(inbox.error) };
        return {
          kind: 'ready',
          pendingBriefs: inbox.status === 'ready' ? pendingCount(inbox.rows) : 0,
        };
    }
  };

  const agents = roster.map((agent) => ({ agent, ...officeStatus(readiness(agent)) }));

  let board: BoardState;
  if (row === null) {
    board =
      selected.status === 'loading'
        ? { kind: 'loading' }
        : selected.status === 'error'
          ? { kind: 'error' }
          : { kind: 'empty' };
  } else if (assessment.isError) {
    board = { kind: 'error' };
  } else if (assessment.data === undefined) {
    board = { kind: 'loading' };
  } else {
    const detail = assessment.data.data;
    board = {
      kind: 'ready',
      board: signalsBoard(detail.customer_source_id, detail.band, signalRows(detail.signals)),
    };
  }

  return {
    agents,
    board,
    trayCount: inbox.status === 'ready' ? inbox.rows.length : null,
    notes: (decisions.data?.data ?? []).map((decision, index) => ({
      ordinal: index + 1,
      decision: decision.decision,
    })),
  };
}
