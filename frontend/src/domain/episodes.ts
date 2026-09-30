/**
 * Episodes (spec §9.5): the ordered steps a replay plays, built only from returned data.
 *
 * Every step carries `source: { route, path }`, the request and the JSON path of the value it
 * shows, and **a step exists only when its data does**: no links, no LINKER step; no conflict, no
 * conflict step; no brief, no delivery. Unit tests resolve every step's path in the recorded
 * fixtures (AC-F-1).
 *
 * The assessment episode dramatises the featured brief, the inbox's first row (§16). The stage
 * numbers follow the code's stage order (DERIVED, `app/decisions/assessment.py`).
 */

import type { BriefPayloadV1 } from '@/api/schemas/briefPayloadV1';
import type { IngestionRunCreatedResponse } from '@/api/schemas/operations';
import type { AssessmentListItem } from '@/api/schemas/risk';

import { bandCounts, describeBandCounts } from './bands';
import type { InboxRow, Snapshot } from './inbox';

export interface Source {
  /** The request, as `METHOD /path`. */
  route: string;
  /** The JSON path of the shown value in that response. `[*]` is every item. */
  path: string;
}

/**
 * - `work`: its agents work at their desks, each with its caption;
 * - `conflict`: its agents meet at the debate table, a red arrow between them;
 * - `deliver`: its agent carries one result to `to`;
 * - `tray`: the CEO's tray holds the delivered briefs;
 * - `handoff`: its agent carries its result to `to`.
 */
export type StepKind = 'work' | 'conflict' | 'deliver' | 'tray' | 'handoff';

export interface Step {
  stage: number;
  kind: StepKind;
  /** The agents that act, by agent id. */
  agents: readonly string[];
  /** Who receives a delivery or a hand-off. */
  to: string | null;
  caption: string;
  source: Source;
  /** The sheets in the CEO's tray once this step has landed. */
  tray: number | null;
}

export interface Episode {
  kind: 'assessment' | 'ingestion';
  steps: Step[];
}

/** The characters of the fingerprint MEMORY's caption shows (§9.5 step 1). */
export const CAPTION_FINGERPRINT = 8;

/** The analysts, by the business function their positions carry. */
const ANALYSTS: Readonly<
  Record<BriefPayloadV1['reconciliation']['ordered_positions'][number]['function'], string>
> = {
  SALES: 'sales',
  SUPPORT: 'support',
};

export interface AssessmentEpisodeInput {
  asOf: string;
  /** The whole list at `asOf`, in API order: `GET /risk/assessments?as_of=`. */
  list: readonly AssessmentListItem[];
  /** The snapshot the inbox shows (§7.2). */
  snapshot: Snapshot;
  /** That snapshot's inbox rows: the first is the featured brief. */
  rows: readonly InboxRow[];
  /** The featured brief's payload, when the snapshot has a brief. */
  featured: { briefId: string; payload: BriefPayloadV1 } | null;
}

export function listRoute(asOf: string): string {
  return `GET /api/v1/risk/assessments?as_of=${asOf}`;
}

export function briefRoute(briefId: string): string {
  return `GET /api/v1/risk/briefs/${briefId}`;
}

export const INGESTION_ROUTE = 'POST /api/v1/ingestion/runs';

/** `items[*]` when the snapshot is the whole list, else the snapshot's own indices. */
function itemsPath(list: readonly AssessmentListItem[], snapshot: Snapshot): string {
  if (snapshot.items.length === list.length) return 'items[*]';
  const ids = new Set(snapshot.items.map((item) => item.id));
  const indices = list.flatMap((item, index) => (ids.has(item.id) ? [index] : []));
  return `items[${indices.join(',')}]`;
}

export function assessmentEpisode(input: AssessmentEpisodeInput): Episode {
  const { asOf, list, snapshot, rows, featured } = input;
  const list_ = listRoute(asOf);
  const indexOf = (assessmentId: string) => list.findIndex((item) => item.id === assessmentId);
  const steps: Step[] = [];
  const first = snapshot.items[0];
  if (first === undefined) return { kind: 'assessment', steps };

  steps.push({
    stage: 1,
    kind: 'work',
    agents: ['memory'],
    to: null,
    caption: `SNAPSHOT ${first.layer1_fingerprint.slice(0, CAPTION_FINGERPRINT)}`,
    source: { route: list_, path: `items[${indexOf(first.id)}].layer1_fingerprint` },
    tray: null,
  });

  const payload = featured?.payload ?? null;
  const brief = featured === null ? '' : briefRoute(featured.briefId);
  const links = payload?.document_evidence.length ?? 0;
  if (payload !== null && links > 0) {
    steps.push({
      stage: 2,
      kind: 'work',
      agents: ['linker'],
      to: null,
      caption: `${links} LINKS · ${payload.customer.id}`,
      source: { route: brief, path: 'payload.document_evidence' },
      tray: null,
    });
  }

  steps.push({
    stage: 3,
    kind: 'work',
    agents: ['signals'],
    to: null,
    caption: describeBandCounts(bandCounts(snapshot.items)),
    source: { route: list_, path: `${itemsPath(list, snapshot)}.band` },
    tray: null,
  });

  if (payload !== null) {
    const reconciliation = payload.reconciliation;
    for (const [fn, agentId] of Object.entries(ANALYSTS)) {
      const index = reconciliation.ordered_positions.findIndex(
        (position) => position.function === fn,
      );
      const position = reconciliation.ordered_positions[index];
      if (position === undefined) continue;
      steps.push({
        stage: 4,
        kind: 'work',
        agents: [agentId],
        to: null,
        caption: position.proposed_action,
        source: {
          route: brief,
          path: `payload.reconciliation.ordered_positions[${index}].proposed_action`,
        },
        tray: null,
      });
    }
    reconciliation.conflicts.forEach((conflict, index) => {
      const agents = [
        ...new Set(conflict.positions.map((position) => ANALYSTS[position.function])),
      ];
      steps.push({
        stage: 5,
        kind: 'conflict',
        agents,
        to: null,
        caption: `CONFLICT ${conflict.object_ref}`,
        source: { route: brief, path: `payload.reconciliation.conflicts[${index}].object_ref` },
        tray: null,
      });
    });
    reconciliation.resolutions.forEach((resolution, index) => {
      steps.push({
        stage: 6,
        kind: 'work',
        agents: ['reconciler'],
        to: null,
        caption: `${resolution.policy_id} → ${resolution.prevailing.function} PREVAILS`,
        source: { route: brief, path: `payload.reconciliation.resolutions[${index}].policy_id` },
        tray: null,
      });
    });
  }

  rows.forEach((row, index) => {
    const item = indexOf(row.assessmentId);
    steps.push({
      stage: 7,
      kind: 'deliver',
      agents: ['brief-writer'],
      to: 'ceo',
      caption: `BRIEF ${row.customerId ?? row.briefId.slice(0, CAPTION_FINGERPRINT)}`,
      source: {
        route: list_,
        path:
          row.customerId === null
            ? `items[${item}].brief_ids`
            : `items[${item}].customer_source_id`,
      },
      tray: index + 1,
    });
  });
  if (rows.length > 0) {
    steps.push({
      stage: 8,
      kind: 'tray',
      agents: ['ceo'],
      to: null,
      caption: `${rows.length} IN TRAY`,
      source: { route: list_, path: `${itemsPath(list, snapshot)}.brief_ids` },
      tray: rows.length,
    });
  }
  return { kind: 'assessment', steps };
}

type EntityResult = IngestionRunCreatedResponse['entities'][number];

/** One entity's outcome, in words: `CUSTOMERS: 0 NEW · 0 UPDATED · 50 UNCHANGED`. */
export function entityCaption(entity: EntityResult): string {
  const name = entity.entity_type.toUpperCase();
  if (entity.status !== 'completed') return `${name}: ${entity.status.toUpperCase()}`;
  const parts = [
    `${entity.records_inserted} NEW`,
    `${entity.records_updated} UPDATED`,
    `${entity.records_unchanged} UNCHANGED`,
  ];
  if (entity.records_rejected > 0) parts.push(`${entity.records_rejected} REJECTED`);
  if (entity.records_failed > 0) parts.push(`${entity.records_failed} FAILED`);
  return `${name}: ${parts.join(' · ')}`;
}

/**
 * The ingestion episode (§9.5, R-F-6): the connector carries the run's own outcome to MEMORY,
 * which files each entity's counts. A `NOOP` run says so in the first caption.
 */
export function ingestionEpisode(source: string, run: IngestionRunCreatedResponse): Episode {
  return {
    kind: 'ingestion',
    steps: [
      {
        stage: 1,
        kind: 'handoff',
        agents: [source],
        to: 'memory',
        caption: `${run.status} · ${run.records_fetched} FETCHED`,
        source: { route: INGESTION_ROUTE, path: 'status' },
        tray: null,
      },
      ...run.entities.map((entity, index): Step => ({
        stage: 2,
        kind: 'work',
        agents: ['memory'],
        to: null,
        caption: entityCaption(entity),
        source: { route: INGESTION_ROUTE, path: `entities[${index}]` },
        tray: null,
      })),
    ],
  };
}

/** Every agent an episode moves, in order of first appearance. The CEO has no body. */
export function participants(episode: Episode): string[] {
  const seen = new Set<string>();
  for (const step of episode.steps)
    for (const agent of step.agents) if (agent !== 'ceo') seen.add(agent);
  return [...seen];
}
