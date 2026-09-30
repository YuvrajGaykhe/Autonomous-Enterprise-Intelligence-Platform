/**
 * Agent panels (spec §8.3, §9.2): a header with the agent's avatar, name tag and module path, its
 * one-line role, its real output in the four states, evidence links and "Show the API call".
 */

import { useQueries, useQuery } from '@tanstack/react-query';
import {
  Bot,
  BriefcaseBusiness,
  Calculator,
  Crown,
  FileText,
  Gavel,
  HardHat,
  Headset,
  Search,
  type LucideIcon,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';

import { ApiError, type ApiCall } from '@/api/client';
import {
  assessmentQuery,
  briefQuery,
  entityTotalQuery,
  healthQuery,
  metricsQuery,
  runErrorsQuery,
  runsQuery,
  sourceHealthQuery,
  sourcesQuery,
} from '@/api/queries';
import type { Brief } from '@/api/risk';
import { ENTITY_TYPES } from '@/api/schemas/entities';
import type { IngestionRunResponse } from '@/api/schemas/operations';
import { useViewLinks } from '@/app/links';
import { COPY } from '@/copy';
import { buildBriefView, derivationViews, signalRows } from '@/domain/briefView';
import { formatTimestamp } from '@/domain/dates';
import { shortFingerprint } from '@/domain/inbox';
import { isMockSource, type Agent, type AgentKind } from '@/domain/roster';
import { useSelectedRow, type SelectedRowState } from '@/data/useSelectedRow';
import { HOSTED } from '@/lib/hosting';
import { AUTO_UNRESOLVED, CeoInbox } from '@/panels/CeoInbox';
import { EmptyState, ErrorState, LoadingState } from '@/states/states';
import { Button } from '@/ui/button';

import { ApiXray } from './ApiXray';
import {
  CitedQuote,
  ConflictSection,
  DissentSection,
  Facts,
  PositionItem,
  Section,
  mono,
} from './BriefDetail';
import { BandChip, DecisionStatusChip, ExecutiveBadge, NameTag } from './chips';
import { DocumentSpanLink, EvidenceList, RecordLink, RecordLinks } from './evidence';
import { RunIngestion } from './RunIngestion';

const AVATARS: Record<AgentKind, LucideIcon> = {
  connector: HardHat,
  memory: Bot,
  linker: Search,
  signals: Calculator,
  sales: BriefcaseBusiness,
  support: Headset,
  reconciler: Gavel,
  briefWriter: FileText,
  ceo: Crown,
};

/** A 404 on a panel's request (§7.6): the not-found state, with a way back to the inbox. */
function NotFoundHere() {
  const links = useViewLinks();
  return (
    <div className="space-y-2">
      <EmptyState message="The API has no such record any more." />
      <Link className="text-sm underline" to={links.inbox()}>
        Return to the inbox
      </Link>
    </div>
  );
}

/** A panel body and the requests behind it. */
interface Body {
  content: ReactNode;
  calls: ApiCall[];
}

function queryBody<T>(
  query: {
    isPending: boolean;
    isError: boolean;
    error: unknown;
    data: T | undefined;
    refetch: () => unknown;
  },
  label: string,
  render: (data: T) => ReactNode,
): ReactNode {
  if (query.isPending) return <LoadingState label={label} />;
  if (query.error instanceof ApiError && query.error.status === 404) return <NotFoundHere />;
  if (query.isError || query.data === undefined) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  return render(query.data);
}

function HealthWord({ status }: { status: string }) {
  return (
    <span className={status === 'healthy' ? 'font-medium text-ok' : 'font-medium text-bad'}>
      {status}
    </span>
  );
}

function when(iso: string | null): ReactNode {
  if (iso === null) return 'not finished';
  const time = formatTimestamp(iso);
  return (
    <time dateTime={iso} title={time.utc}>
      {time.local}
    </time>
  );
}

function RunErrors({ runId }: { runId: string }) {
  const query = useQuery(runErrorsQuery(runId));
  return (
    <div className="space-y-2">
      {queryBody(query, 'the run errors', ({ data }) =>
        data.length === 0 ? (
          <p className="text-xs text-muted-foreground">This run recorded no error.</p>
        ) : (
          <ul className="space-y-1 text-xs">
            {data.map((error) => (
              <li key={error.id} className="rounded border p-2">
                <span className="font-mono font-semibold">{error.severity}</span>{' '}
                <span className="font-mono">{error.code ?? 'no code'}</span>: {error.message}
                {error.source_id !== null && (
                  <span className="font-mono text-muted-foreground">
                    {' '}
                    ({error.source_entity} {error.source_id})
                  </span>
                )}
              </li>
            ))}
          </ul>
        ),
      )}
      {query.data !== undefined && <ApiXray calls={query.data.calls} />}
    </div>
  );
}

function RunRow({ run }: { run: IngestionRunResponse }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="space-y-2 rounded-lg border p-3 text-sm">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-mono font-semibold">{run.status}</span>
        <span>{run.source_entity ?? 'every entity type'}</span>
        <span className="text-muted-foreground">{run.mode}</span>
        <span className="text-muted-foreground">started {when(run.started_at)}</span>
      </p>
      <p className="font-mono text-xs">
        fetched {run.records_fetched} · inserted {run.records_inserted} · updated{' '}
        {run.records_updated} · unchanged {run.records_unchanged} · rejected {run.records_rejected}{' '}
        · failed {run.records_failed} · warnings {run.warnings}
      </p>
      {run.error_summary !== null && <p className="text-xs text-bad">{run.error_summary}</p>}
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {open ? 'Hide errors' : 'Show errors'}
      </Button>
      {open && <RunErrors runId={run.run_id} />}
    </li>
  );
}

/** The most recent runs a connector panel lists. */
export const RECENT_RUNS = 10;

function useConnectorBody(source: string): Body {
  const sources = useQuery(sourcesQuery());
  const health = useQuery(sourceHealthQuery(source));
  const runs = useQuery(runsQuery());
  const calls = [
    ...(sources.data?.calls ?? []),
    ...(health.data?.calls ?? []),
    ...(runs.data?.calls ?? []),
  ];
  const content = (
    <div className="space-y-4">
      <Section id="connector-capabilities" title="Capabilities">
        {queryBody(sources, 'the capabilities', ({ data }) => {
          const summary = data.find((item) => item.source === source);
          if (summary === undefined)
            return <EmptyState message={`No source named ${source} is configured.`} />;
          const capabilities = summary.capabilities;
          return (
            <Facts
              rows={[
                [
                  'Source type',
                  <span key="t" className={mono}>
                    {summary.source_type}
                  </span>,
                ],
                [
                  'Entity types',
                  <span key="e" className={mono}>
                    {capabilities.supported_entity_types.join(', ')}
                  </span>,
                ],
                ['Incremental', capabilities.supports_incremental ? 'yes' : 'no'],
                ['Health check', capabilities.supports_health_check ? 'yes' : 'no'],
                ['Read only', capabilities.read_only ? 'yes' : 'no'],
              ]}
            />
          );
        })}
      </Section>
      <Section id="connector-health" title="Health check">
        {queryBody(health, 'the health check', ({ data }) => (
          <>
            <Facts
              rows={[
                ['Status', <HealthWord key="s" status={data.status} />],
                [
                  'Latency',
                  data.latency_ms === null ? 'not measured' : `${Math.round(data.latency_ms)} ms`,
                ],
                ['Error type', data.error_type ?? 'none'],
                ['Checked at', when(data.checked_at)],
              ]}
            />
            {/* The hosted site shows the real result, and says why (§16). */}
            {HOSTED && isMockSource(source) && (
              <p className="mt-2 text-sm text-muted-foreground">{COPY.mockSourceHostedOnly}</p>
            )}
          </>
        ))}
      </Section>
      <Section id="connector-ingest" title="Run ingestion">
        <RunIngestion source={source} healthy={health.data?.data.status === 'healthy'} />
      </Section>
      <Section id="connector-runs" title="Latest ingestion runs">
        {queryBody(runs, 'the ingestion runs', ({ data }) => {
          const mine = data.filter((run) => run.source_system === source).slice(0, RECENT_RUNS);
          return mine.length === 0 ? (
            <EmptyState message="No ingestion run from this source yet." />
          ) : (
            <ul className="space-y-2">
              {mine.map((run) => (
                <RunRow key={run.run_id} run={run} />
              ))}
            </ul>
          );
        })}
      </Section>
    </div>
  );
  return { content, calls };
}

function useMemoryBody(): Body {
  const health = useQuery(healthQuery());
  const totals = useQueries({ queries: ENTITY_TYPES.map((type) => entityTotalQuery(type)) });
  const metrics = useQuery(metricsQuery());
  const selected = useSelectedRow();
  const calls = [
    ...(health.data === undefined ? [] : [health.data.call]),
    ...totals.flatMap((query) => query.data?.calls ?? []),
    ...(metrics.data?.calls ?? []),
    ...selected.calls,
  ];
  const failed = totals.find((query) => query.isError);
  let recordTotals: ReactNode;
  if (failed !== undefined) {
    recordTotals = (
      <ErrorState
        error={failed.error}
        onRetry={() => totals.forEach((query) => void query.refetch())}
      />
    );
  } else if (totals.some((query) => query.data === undefined)) {
    recordTotals = <LoadingState label="the record totals" lines={4} />;
  } else if (totals.every((query) => query.data?.data === 0)) {
    recordTotals = <EmptyState message={COPY.memoryNoRecords} />;
  } else {
    recordTotals = (
      <Facts
        rows={ENTITY_TYPES.map(
          (type, index) =>
            [
              type,
              <span key={type} className={mono}>
                {totals[index]?.data?.data}
              </span>,
            ] as const,
        )}
      />
    );
  }
  const content = (
    <div className="space-y-4">
      <Section id="memory-health" title="Database">
        {queryBody(health, 'the health', ({ data }) => (
          <Facts
            rows={[
              ['API', <HealthWord key="a" status={data.status} />],
              ['Database', data.checks.database],
              [
                'Version',
                <span key="v" className={mono}>
                  {data.version}
                </span>,
              ],
            ]}
          />
        ))}
      </Section>
      <Section id="memory-records" title="Canonical records">
        {recordTotals}
      </Section>
      <Section id="memory-metrics" title="Ingestion metrics">
        {queryBody(metrics, 'the metrics', ({ data }) => (
          <Facts
            rows={[
              [
                'Runs',
                <span key="r" className={mono}>
                  {data.totals.runs_total}
                </span>,
              ],
              [
                'Runs by status',
                <span key="s" className={mono}>
                  {Object.entries(data.totals.runs_by_status)
                    .map(([status, count]) => `${status} ${count}`)
                    .join(' · ')}
                </span>,
              ],
              [
                'Records fetched',
                <span key="f" className={mono}>
                  {data.totals.records_fetched_total}
                </span>,
              ],
              [
                'Records rejected',
                <span key="j" className={mono}>
                  {data.totals.records_rejected_total}
                </span>,
              ],
              [
                'Validation errors',
                <span key="v" className={mono}>
                  {data.totals.validation_errors_total}
                </span>,
              ],
            ]}
          />
        ))}
      </Section>
      <Section id="memory-snapshot" title="Snapshot">
        {selected.status === 'ready' ? (
          <Facts
            rows={[
              [
                'as_of',
                <span key="a" className={mono}>
                  {selected.asOf}
                </span>,
              ],
              [
                'Layer 1 fingerprint',
                <span key="f" className={`${mono} break-all`}>
                  {selected.snapshot.key.layer1_fingerprint}
                </span>,
              ],
            ]}
          />
        ) : (
          <SelectionFallback state={selected} />
        )}
      </Section>
    </div>
  );
  return { content, calls };
}

/** What a panel that needs the selected customer shows until there is one. */
function SelectionFallback({ state }: { state: Exclude<SelectedRowState, { status: 'ready' }> }) {
  switch (state.status) {
    case 'auto-unresolved':
      return <EmptyState message={AUTO_UNRESOLVED} />;
    case 'loading':
      return <LoadingState label="the selected brief" />;
    case 'error':
      return <ErrorState error={state.error} onRetry={state.retry} />;
    case 'no-assessment':
      return <EmptyState message={COPY.inboxNoAssessment} />;
    case 'no-brief':
      return <EmptyState message={COPY.inboxNoBrief} />;
  }
}

function SelectedHeader({ state }: { state: Extract<SelectedRowState, { status: 'ready' }> }) {
  const links = useViewLinks();
  const { row } = state;
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted-foreground">Showing</span>
      <Link className="font-medium underline" to={links.brief(row.briefId)}>
        {row.customerName ?? row.customerId ?? 'the selected brief'}
      </Link>
      <span className="font-mono text-xs text-muted-foreground">{row.customerId}</span>
      <BandChip band={row.band} />
      {row.executiveWorthy && <ExecutiveBadge />}
      <DecisionStatusChip status={row.decisionStatus} />
      <span className="font-mono text-xs text-muted-foreground">
        as_of {state.asOf} · snapshot {shortFingerprint(state.snapshot.key.layer1_fingerprint)}
      </span>
    </p>
  );
}

/** A body built from the selected customer's brief (LINKER, RECONCILER, BRIEF_WRITER). */
function useBriefBody(render: (brief: Extract<Brief, { supported: true }>) => ReactNode): Body {
  const selected = useSelectedRow();
  const brief = useQuery({
    ...briefQuery(selected.status === 'ready' ? selected.row.briefId : ''),
    enabled: selected.status === 'ready',
  });
  const calls = [...selected.calls, ...(brief.data?.calls ?? [])];
  if (selected.status !== 'ready')
    return { content: <SelectionFallback state={selected} />, calls };
  const content = (
    <div className="space-y-4">
      <SelectedHeader state={selected} />
      {queryBody(brief, 'the brief', ({ data }) =>
        data.supported ? (
          render(data)
        ) : (
          <EmptyState message={COPY.unsupportedBrief.replace('{n}', String(data.payloadVersion))} />
        ),
      )}
    </div>
  );
  return { content, calls };
}

function LinkerContent({ brief }: { brief: Extract<Brief, { supported: true }> }) {
  const { payload } = brief;
  const source = payload.scope.source_system;
  return (
    <>
      <Section id="linker-links" title="Document links">
        {payload.document_evidence.length === 0 ? (
          <EmptyState message="The linker found no document naming this customer in this snapshot." />
        ) : (
          <ul className="space-y-2">
            {payload.document_evidence.map((link, index) => (
              <li key={index} className="space-y-1 rounded-lg border p-3 text-sm">
                <p>
                  <RecordLink
                    entity={link.source.entity}
                    id={link.source.id}
                    sourceSystem={source}
                  />{' '}
                  by <span className={mono}>{link.basis}</span> ({link.edge_basis}),{' '}
                  {link.confidence} confidence, matching &ldquo;{link.matched_token}&rdquo;
                </p>
                <EvidenceList evidence={link.evidence} sourceSystem={source} />
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section id="linker-spans" title="Cited spans">
        {payload.cited_spans.length === 0 ? (
          <EmptyState message="No span is cited in this brief." />
        ) : (
          <ul className="space-y-3">
            {payload.cited_spans.map((span) => (
              <li key={span.target} className="space-y-1">
                <p className="text-sm">
                  <span className={`${mono} font-semibold`}>{span.target}</span>,{' '}
                  <DocumentSpanLink
                    documentId={span.citation.document_id}
                    start={span.citation.start}
                    end={span.citation.end}
                    sourceSystem={source}
                  />
                </p>
                <CitedQuote
                  documentId={span.citation.document_id}
                  start={span.citation.start}
                  end={span.citation.end}
                  sourceSystem={source}
                />
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}

function ReconcilerContent({ brief }: { brief: Extract<Brief, { supported: true }> }) {
  const view = buildBriefView(brief.response, brief.payload);
  const worthiness = view.risk.worthiness;
  return (
    <>
      <ConflictSection view={view} />
      <DissentSection view={view} />
      <Section id="reconciler-worthiness" title="Executive worthiness">
        <Facts
          rows={[
            ['Executive-worthy', worthiness.executive_worthy ? 'yes' : 'no'],
            ['Band', <BandChip key="b" band={worthiness.band} />],
            ['Active deals', String(worthiness.active_deal_count)],
            ['Active projects', String(worthiness.active_project_count)],
          ]}
        />
      </Section>
    </>
  );
}

function BriefWriterContent({ brief }: { brief: Extract<Brief, { supported: true }> }) {
  const { response } = brief;
  return (
    <>
      <Section id="writer-facts" title="The stored brief">
        <Facts
          rows={[
            [
              'Payload hash',
              <span key="h" className={`${mono} break-all`}>
                {response.payload_hash}
              </span>,
            ],
            ['Policy version', String(response.policy_version)],
            [
              'Template version',
              <span key="t" className={mono}>
                {response.template_version}
              </span>,
            ],
            ['Citations', String(response.citations.length)],
          ]}
        />
      </Section>
      <Section id="writer-narrative" title="Narrative">
        <pre className="rounded-lg border bg-muted/40 p-3 font-mono text-xs break-words whitespace-pre-wrap">
          {response.narrative}
        </pre>
      </Section>
    </>
  );
}

/** A body built from the selected customer's assessment (SIGNALS, SALES, SUPPORT). */
function useAssessmentBody(kind: 'signals' | 'sales' | 'support'): Body {
  const selected = useSelectedRow();
  const ready = selected.status === 'ready';
  const assessment = useQuery({
    ...assessmentQuery(ready ? selected.row.assessmentId : ''),
    enabled: ready,
  });
  const brief = useQuery({
    ...briefQuery(ready ? selected.row.briefId : ''),
    enabled: ready && kind === 'signals',
  });
  const calls = [
    ...selected.calls,
    ...(assessment.data?.calls ?? []),
    ...(kind === 'signals' ? (brief.data?.calls ?? []) : []),
  ];
  if (selected.status !== 'ready')
    return { content: <SelectionFallback state={selected} />, calls };
  const source = selected.snapshot.key.source_system;
  const content = (
    <div className="space-y-4">
      <SelectedHeader state={selected} />
      {queryBody(assessment, 'the assessment', ({ data }) => {
        if (kind !== 'signals') {
          const functionName = kind === 'sales' ? 'SALES' : 'SUPPORT';
          const positions = data.positions.filter((position) => position.function === functionName);
          return (
            <Section id={`${kind}-positions`} title={`${functionName} positions`}>
              {positions.length === 0 ? (
                <EmptyState message={`${functionName} stated no position on this customer.`} />
              ) : (
                <ol className="space-y-2">
                  {positions.map((position) => (
                    <PositionItem
                      key={position.ordinal}
                      position={{ ...position, evidence: position.citations }}
                      sourceSystem={source}
                    />
                  ))}
                </ol>
              )}
            </Section>
          );
        }
        return (
          <>
            <Section id="signals-band" title="Band and rules">
              <Facts
                rows={[
                  ['Band', <BandChip key="b" band={data.band} />],
                  [
                    'Satisfied band rules',
                    <span key="r" className={mono}>
                      {data.satisfied_rules.length === 0 ? 'none' : data.satisfied_rules.join(', ')}
                    </span>,
                  ],
                ]}
              />
              <p className="text-xs text-muted-foreground">{COPY.bandLegend}</p>
            </Section>
            <Section id="signals-values" title="Signals">
              <table className="w-full text-sm">
                <caption className="sr-only">Signal values</caption>
                <tbody>
                  {signalRows(data.signals).map((row) => (
                    <tr key={row.id} className="border-t">
                      <th scope="row" className={`${mono} pr-3 text-left font-normal`}>
                        {row.id} {row.key}
                      </th>
                      <td className={mono}>{row.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
            <Section id="signals-derivations" title="Derivations">
              {queryBody(brief, 'the derivations', ({ data: loaded }) =>
                loaded.supported ? (
                  <ul className="space-y-2">
                    {derivationViews(loaded.payload.support_evidence.derivations).map(
                      (derivation) => (
                        <li key={derivation.fact} className="text-sm">
                          <span className={mono}>
                            {derivation.fact} = {derivation.value}
                          </span>
                          , counting{' '}
                          <RecordLinks
                            entity="support_tickets"
                            ids={derivation.ticketIds}
                            sourceSystem={source}
                          />
                          <span className="block text-xs text-muted-foreground">
                            rule: {derivation.rule}
                          </span>
                        </li>
                      ),
                    )}
                  </ul>
                ) : (
                  <EmptyState
                    message={COPY.unsupportedBrief.replace('{n}', String(loaded.payloadVersion))}
                  />
                ),
              )}
            </Section>
          </>
        );
      })}
    </div>
  );
  return { content, calls };
}

function useCeoBody(): Body {
  return { content: <CeoInbox />, calls: [] };
}

/** Each agent's body, as a component so each keeps its own hooks. */
function ConnectorBody({ source }: { source: string }) {
  return <Framed body={useConnectorBody(source)} />;
}
function MemoryBody() {
  return <Framed body={useMemoryBody()} />;
}
function LinkerBody() {
  return (
    <Framed
      body={useBriefBody((brief) => (
        <LinkerContent brief={brief} />
      ))}
    />
  );
}
function ReconcilerBody() {
  return (
    <Framed
      body={useBriefBody((brief) => (
        <ReconcilerContent brief={brief} />
      ))}
    />
  );
}
function BriefWriterBody() {
  return (
    <Framed
      body={useBriefBody((brief) => (
        <BriefWriterContent brief={brief} />
      ))}
    />
  );
}
function AssessmentBody({ kind }: { kind: 'signals' | 'sales' | 'support' }) {
  return <Framed body={useAssessmentBody(kind)} />;
}
function CeoBody() {
  return <Framed body={useCeoBody()} xray={false} />;
}

function Framed({ body, xray = true }: { body: Body; xray?: boolean }) {
  return (
    <div className="space-y-4">
      {body.content}
      {xray && <ApiXray calls={body.calls} />}
    </div>
  );
}

function Content({ agent }: { agent: Agent }) {
  switch (agent.kind) {
    case 'connector':
      return <ConnectorBody source={agent.id} />;
    case 'memory':
      return <MemoryBody />;
    case 'linker':
      return <LinkerBody />;
    case 'signals':
      return <AssessmentBody kind="signals" />;
    case 'sales':
      return <AssessmentBody kind="sales" />;
    case 'support':
      return <AssessmentBody kind="support" />;
    case 'reconciler':
      return <ReconcilerBody />;
    case 'briefWriter':
      return <BriefWriterBody />;
    case 'ceo':
      return <CeoBody />;
  }
}

export function AgentHeader({ agent }: { agent: Agent }) {
  const Avatar = AVATARS[agent.kind];
  return (
    <header className="flex items-start gap-3">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-full border bg-muted">
        <Avatar aria-hidden="true" className="size-6" />
      </span>
      <div className="min-w-0 space-y-1">
        <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold">
          <NameTag tag={agent.tag} />
        </h1>
        <p className="font-mono text-xs text-muted-foreground">{agent.module}</p>
        <p className="text-sm">{agent.role}</p>
      </div>
    </header>
  );
}

/** One agent's panel. */
export function AgentPanel({ agent }: { agent: Agent }) {
  return (
    <div className="space-y-4">
      <AgentHeader agent={agent} />
      <Content key={agent.id} agent={agent} />
    </div>
  );
}
