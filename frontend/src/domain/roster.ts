/**
 * The agent roster and the rooms (spec §9.1, §9.2, §9.13; the mapping is DIRECTED, the ids and
 * room names are PROPOSED, §8.1).
 *
 * The roster is the fixed VS-01 set plus one connector agent per entry of `GET /sources`, in API
 * order. Connectors are never hard-coded. Future slices appear only as locked rooms (D-F-4).
 */

import { ROLE_LINES } from '@/copy';

export type AgentKind =
  | 'connector'
  | 'memory'
  | 'linker'
  | 'signals'
  | 'sales'
  | 'support'
  | 'reconciler'
  | 'briefWriter'
  | 'ceo';

export type RoomId =
  | 'data-dock'
  | 'evidence-lab'
  | 'signals-desk'
  | 'analyst-bullpen'
  | 'debate-table'
  | 'brief-studio'
  | 'ceo-office'
  | 'break-area'
  | 'pipeline-room'
  | 'account-360'
  | 'war-room'
  | 'copilot-desk';

export interface Room {
  id: RoomId;
  name: string;
  /** The slice that opens a locked room; null for an open room. */
  opensWith: number | null;
}

/** Every room, open rooms first (§9.1). */
export const ROOMS: readonly Room[] = [
  { id: 'data-dock', name: 'Data Dock', opensWith: null },
  { id: 'evidence-lab', name: 'Evidence Lab', opensWith: null },
  { id: 'signals-desk', name: 'Signals Desk', opensWith: null },
  { id: 'analyst-bullpen', name: 'Analyst Bullpen', opensWith: null },
  { id: 'debate-table', name: 'Debate Table', opensWith: null },
  { id: 'brief-studio', name: 'Brief Studio', opensWith: null },
  { id: 'ceo-office', name: 'CEO Corner Office', opensWith: null },
  { id: 'break-area', name: 'Break Area', opensWith: null },
  { id: 'pipeline-room', name: 'Pipeline Room', opensWith: 2 },
  { id: 'account-360', name: 'Account 360', opensWith: 3 },
  { id: 'war-room', name: 'War Room', opensWith: 4 },
  { id: 'copilot-desk', name: 'Copilot Desk', opensWith: 5 },
];

export function isLocked(room: Room): boolean {
  return room.opensWith !== null;
}

export interface Agent {
  /** The URL id (§8.1): a connector's source name, or a fixed id. */
  id: string;
  kind: AgentKind;
  /** The in-world name tag. */
  tag: string;
  /** The component the agent stands for. */
  module: string;
  role: string;
  room: RoomId;
}

/** The fixed VS-01 agents, in the pipeline's stage order (DERIVED, `app/decisions/assessment.py`). */
export const FIXED_AGENTS: readonly Agent[] = [
  {
    id: 'memory',
    kind: 'memory',
    tag: 'MEMORY',
    module: 'Layer 1 PostgreSQL',
    role: ROLE_LINES.memory,
    room: 'data-dock',
  },
  {
    id: 'linker',
    kind: 'linker',
    tag: 'LINKER_AGENT',
    module: 'app/evidence/linker.py',
    role: ROLE_LINES.linker,
    room: 'evidence-lab',
  },
  {
    id: 'signals',
    kind: 'signals',
    tag: 'SIGNALS_AGENT',
    module: 'app/intelligence/signals.py, bands.py',
    role: ROLE_LINES.signals,
    room: 'signals-desk',
  },
  {
    id: 'sales',
    kind: 'sales',
    tag: 'SALES_AGENT',
    module: 'app/analysts/commercial.py',
    role: ROLE_LINES.sales,
    room: 'analyst-bullpen',
  },
  {
    id: 'support',
    kind: 'support',
    tag: 'SUPPORT_AGENT',
    module: 'app/analysts/support_risk.py',
    role: ROLE_LINES.support,
    room: 'analyst-bullpen',
  },
  {
    id: 'reconciler',
    kind: 'reconciler',
    tag: 'RECONCILER_AGENT',
    module: 'app/decisions/reconciler.py, policy.py, conflicts.py',
    role: ROLE_LINES.reconciler,
    room: 'debate-table',
  },
  {
    id: 'brief-writer',
    kind: 'briefWriter',
    tag: 'BRIEF_WRITER',
    module: 'app/decisions/brief.py, payload.py',
    role: ROLE_LINES.briefWriter,
    room: 'brief-studio',
  },
  {
    id: 'ceo',
    kind: 'ceo',
    tag: 'CEO',
    module: 'app/decisions/approval.py',
    role: ROLE_LINES.ceo,
    room: 'ceo-office',
  },
];

/** One connector agent for one configured source: `csv_demo` → `CSV_DEMO_AGENT`. */
export function connectorAgent(source: string): Agent {
  return {
    id: source,
    kind: 'connector',
    tag: `${source.toUpperCase()}_AGENT`,
    module: 'app/connectors/*',
    role: ROLE_LINES.connector,
    room: 'data-dock',
  };
}

/**
 * The roster: every source's connector in API order, then the fixed agents. A source whose name
 * is a fixed agent's id would be unreachable by URL, so the fixed agent keeps the id.
 */
export function rosterFor(sources: readonly { source: string }[]): Agent[] {
  const fixedIds = new Set(FIXED_AGENTS.map((agent) => agent.id));
  return [
    ...sources
      .filter((item) => !fixedIds.has(item.source))
      .map((item) => connectorAgent(item.source)),
    ...FIXED_AGENTS,
  ];
}

export function agentById(roster: readonly Agent[], id: string): Agent | null {
  return roster.find((agent) => agent.id === id) ?? null;
}
