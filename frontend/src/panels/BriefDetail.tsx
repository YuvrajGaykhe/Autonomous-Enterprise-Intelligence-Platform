/**
 * Brief detail (spec §7.3, §8.4): every section of one brief, in the brief's own order, with every
 * evidence item linked to what it cites. The narrative is shown verbatim; the page never re-renders
 * it. A payload version this frontend does not know renders no section at all (§6.4).
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';
import { Link, type To } from 'react-router';

import { ApiError } from '@/api/client';
import { briefQuery, decisionsQuery, entitiesQuery, type Fetched } from '@/api/queries';
import type { Brief } from '@/api/risk';
import type { Position } from '@/api/schemas/briefPayloadV1';
import type { DecisionResponse } from '@/api/schemas/risk';
import { COPY, fill } from '@/copy';
import { buildBriefView, type BriefView } from '@/domain/briefView';
import { customerKey, customerNames } from '@/domain/inbox';
import { formatMoney } from '@/domain/money';
import { findRecord } from '@/domain/records';
import { citableText, quote, spanFits } from '@/domain/spans';
import { useSession } from '@/state/session';
import { EmptyState, ErrorState, LoadingState } from '@/states/states';
import { Card, CardTitle } from '@/ui/card';

import { ApiXray } from './ApiXray';
import { BandChip, DecisionStatusChip, ExecutiveBadge } from './chips';
import { DecisionChain } from './DecisionChain';
import { DecisionPanel } from './DecisionPanel';
import { DocumentSpanLink, EvidenceList, RecordLink, RecordLinks } from './evidence';

export function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <Card aria-labelledby={id} className="space-y-3">
      <CardTitle id={id}>{title}</CardTitle>
      {children}
    </Card>
  );
}

export function Facts({ rows }: { rows: readonly (readonly [string, ReactNode])[] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="min-w-0 break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export const mono = 'font-mono text-xs';

export function PositionItem({
  position,
  sourceSystem,
  lead,
}: {
  position: Position;
  sourceSystem: string;
  lead?: ReactNode;
}) {
  return (
    <li className="space-y-1 rounded-lg border p-3">
      <p className="text-sm">
        {lead}
        <span className="font-semibold">{position.function}</span>{' '}
        <span className={mono}>{position.stance}</span>{' '}
        <span className={`${mono} font-semibold`}>{position.proposed_action}</span> on{' '}
        <span className={mono}>{position.object_ref}</span>
      </p>
      <p className="text-sm text-muted-foreground">{position.rationale}</p>
      <EvidenceList evidence={position.evidence} sourceSystem={sourceSystem} />
    </li>
  );
}

export function CitedQuote({
  documentId,
  start,
  end,
  sourceSystem,
}: {
  documentId: string;
  start: number;
  end: number;
  sourceSystem: string;
}) {
  const documents = useQuery(entitiesQuery('documents'));
  if (documents.isPending) return <LoadingState label={`the quote from ${documentId}`} lines={1} />;
  if (documents.isError) {
    return <ErrorState error={documents.error} onRetry={() => void documents.refetch()} />;
  }
  const document = findRecord(documents.data.data, sourceSystem, documentId);
  const text = document === null ? null : citableText(document);
  if (text === null || !spanFits(text, start, end)) {
    return (
      <p className="text-sm text-muted-foreground">The cited text cannot be read from Layer 1.</p>
    );
  }
  const cited = quote(text, start, end);
  return (
    <blockquote className="border-l-4 border-band-watch pl-3 text-sm">
      &ldquo;{cited.text}&rdquo;
      {cited.truncated && <span className="text-muted-foreground"> [truncated]</span>}
    </blockquote>
  );
}

function IdentitySection({ view, name }: { view: BriefView; name: string | null }) {
  const { identity } = view;
  return (
    <Section id="brief-identity" title="Identity">
      <Facts
        rows={[
          [
            'Customer',
            <span key="c">
              {name ?? 'Name not in Layer 1'}{' '}
              <RecordLink
                entity="customers"
                id={identity.customerId}
                sourceSystem={identity.sourceSystem}
              />
            </span>,
          ],
          [
            'Source system',
            <span key="s" className={mono}>
              {identity.sourceSystem}
            </span>,
          ],
          [
            'As of',
            <span key="a" className={mono}>
              {identity.asOf}
            </span>,
          ],
          [
            'Layer 1 fingerprint',
            <span key="f" className={`${mono} break-all`}>
              {identity.fingerprint}
            </span>,
          ],
          [
            'Versions',
            <span key="v" className={mono}>
              payload {identity.versions.payload}, rules {identity.versions.rules}, linker{' '}
              {identity.versions.linker}, policy {identity.versions.policy}
            </span>,
          ],
        ]}
      />
    </Section>
  );
}

function RiskSection({ view }: { view: BriefView }) {
  const { risk } = view;
  const worthiness = risk.worthiness;
  return (
    <Section id="brief-risk" title="Risk state and why">
      <Facts
        rows={[
          ['Band', <BandChip key="b" band={risk.band} />],
          [
            'Satisfied band rules',
            <span key="r" className={mono}>
              {risk.satisfiedRules.length === 0 ? 'none' : risk.satisfiedRules.join(', ')}
            </span>,
          ],
          [
            'Executive-worthy',
            <span key="e">
              {worthiness.executive_worthy ? 'yes' : 'no'} (band {worthiness.band}, active deal
              count {worthiness.active_deal_count}, active project count{' '}
              {worthiness.active_project_count})
            </span>,
          ],
        ]}
      />
      <p className="text-xs text-muted-foreground">{COPY.bandLegend}</p>
    </Section>
  );
}

function SignalsSection({ view }: { view: BriefView }) {
  const { signals, identity } = view;
  const source = identity.sourceSystem;
  return (
    <Section id="brief-signals" title="Signals and derivations">
      <table className="w-full text-sm">
        <caption className="sr-only">Signals S1 to S15</caption>
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th scope="col" className="pr-3 font-normal">
              Signal
            </th>
            <th scope="col" className="pr-3 font-normal">
              Name
            </th>
            <th scope="col" className="font-normal">
              Value
            </th>
          </tr>
        </thead>
        <tbody>
          {signals.rows.map((row) => (
            <tr key={row.id} className="border-t">
              <td className={`${mono} pr-3`}>{row.id}</td>
              <td className={`${mono} pr-3`}>{row.key}</td>
              <td className={mono}>{row.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Facts
        rows={[
          [
            'Escalation window',
            signals.escalationWindow === null ? (
              'none'
            ) : (
              <span key="w">
                {signals.escalationWindow.start} to {signals.escalationWindow.end}, ticket count{' '}
                {signals.escalationWindow.count}
              </span>
            ),
          ],
          [
            'Ticket span',
            signals.ticketSpan === null ? (
              'none'
            ) : (
              <span key="t" className="space-y-1">
                <span className="block">
                  a {signals.ticketSpan.ticket_span_days}-day span from{' '}
                  {signals.ticketSpan.first_ticket_date} to {signals.ticketSpan.last_ticket_date},
                  ticket count {signals.ticketSpan.ticket_count}:{' '}
                  <RecordLinks
                    entity="support_tickets"
                    ids={signals.ticketSpan.ticket_ids}
                    sourceSystem={source}
                  />
                </span>
                <span className="block text-xs text-muted-foreground">
                  rule: {signals.ticketSpan.rule}
                </span>
              </span>
            ),
          ],
        ]}
      />
      <h3 className="text-sm font-semibold">Derivations</h3>
      <ul className="space-y-2">
        {signals.derivations.map((derivation) => (
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
            {derivation.categories !== null && (
              <span className="block text-xs">
                category counts{' '}
                {derivation.categories.counts
                  .map((entry) => `${entry.category} ${entry.count}`)
                  .join(', ') || 'none'}
                ; lookback {derivation.categories.lookback}
              </span>
            )}
            <span className="block text-xs text-muted-foreground">rule: {derivation.rule}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function EvidenceSections({
  view,
  customerName,
}: {
  view: BriefView;
  customerName: string | null;
}) {
  const { evidence, identity } = view;
  const source = identity.sourceSystem;
  return (
    <>
      <Section id="brief-tickets" title="Evidence: tickets">
        {evidence.tickets.length === 0 ? (
          <p className="text-sm text-muted-foreground">No ticket is cited.</p>
        ) : (
          <ul className="space-y-2">
            {evidence.tickets.map((ticket) => (
              <li key={ticket.id} className="space-y-1 rounded-lg border p-3 text-sm">
                <p>
                  <RecordLink entity="support_tickets" id={ticket.id} sourceSystem={source} />:
                  created {ticket.created_date}, priority {ticket.priority ?? 'none'}, category{' '}
                  {ticket.category ?? 'none'}, open {ticket.is_open ? 'yes' : 'no'}, breaches SLA{' '}
                  {ticket.breaches_sla ? 'yes' : 'no'}
                </p>
                <EvidenceList evidence={ticket.evidence} sourceSystem={source} />
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section id="brief-documents" title="Evidence: documents">
        <p className="text-xs text-muted-foreground">This snapshot and linker version only.</p>
        {evidence.documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">No document links to this customer.</p>
        ) : (
          <ul className="space-y-2">
            {evidence.documents.map((link, index) => (
              <li key={index} className="space-y-1 rounded-lg border p-3 text-sm">
                <p>
                  <RecordLink
                    entity={link.source.entity}
                    id={link.source.id}
                    sourceSystem={source}
                  />{' '}
                  names {customerName ?? link.target.id} ({link.target.id}) by{' '}
                  <span className={mono}>{link.basis}</span>, {link.confidence} confidence, matching
                  &ldquo;{link.matched_token}&rdquo;
                </p>
                <EvidenceList evidence={link.evidence} sourceSystem={source} />
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section id="brief-deals" title="Evidence: deals">
        {evidence.deals.length === 0 ? (
          <p className="text-sm text-muted-foreground">No deal is cited.</p>
        ) : (
          <ul className="space-y-2">
            {evidence.deals.map((deal) => (
              <li key={deal.id} className="space-y-1 rounded-lg border p-3 text-sm">
                <p>
                  <RecordLink entity="deals" id={deal.id} sourceSystem={source} />: stage{' '}
                  {deal.stage}, probability {deal.probability}, amount {formatMoney(deal.amount)}
                </p>
                <EvidenceList evidence={deal.evidence} sourceSystem={source} />
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section id="brief-quotes" title="Evidence: cited quotes">
        {evidence.quotes.length === 0 ? (
          <p className="text-sm text-muted-foreground">No span is cited.</p>
        ) : (
          <ul className="space-y-3">
            {evidence.quotes.map((span) => (
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

function CommercialSection({ view }: { view: BriefView }) {
  const { commercial, identity } = view;
  return (
    <Section id="brief-commercial" title="Commercial context (per currency)">
      <Facts
        rows={[
          [
            'Active deals',
            commercial.activeDeals.length === 0 ? (
              'none'
            ) : (
              <ul key="d">
                {commercial.activeDeals.map((deal) => (
                  <li key={deal.id}>
                    <RecordLink entity="deals" id={deal.id} sourceSystem={identity.sourceSystem} />:
                    stage {deal.stage}, probability {deal.probability}, amount {deal.amount}
                  </li>
                ))}
              </ul>
            ),
          ],
          [
            'Exposure by currency (S12)',
            commercial.exposure.length === 0 ? (
              'none'
            ) : (
              <ul key="x" className={mono}>
                {commercial.exposure.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            ),
          ],
          ['Active projects (S13)', String(commercial.activeProjectCount)],
        ]}
      />
      <p className="text-xs text-muted-foreground">
        Amounts are shown per currency. No total is computed across currencies.
      </p>
    </Section>
  );
}

export function ConflictSection({ view }: { view: BriefView }) {
  const source = view.identity.sourceSystem;
  return (
    <Section id="brief-conflict" title="Conflict and how it was resolved">
      {view.conflicts.length === 0 ? (
        <p className="text-sm text-muted-foreground">No two functions conflict on this customer.</p>
      ) : (
        <ul className="space-y-3">
          {view.conflicts.map((conflict) => (
            <li key={conflict.object_ref} className="space-y-2">
              <p className="text-sm font-medium">
                Conflict over <span className={mono}>{conflict.object_ref}</span>
              </p>
              <ul className="space-y-2">
                {conflict.positions.map((position, index) => (
                  <PositionItem key={index} position={position} sourceSystem={source} />
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {view.resolutions.map((resolution) => (
        <div
          key={resolution.policy_id + resolution.conflict.object_ref}
          className="space-y-1 text-sm"
        >
          <p>
            Resolved by policy{' '}
            <span className={`${mono} font-semibold`}>{resolution.policy_id}</span>:{' '}
            <span className={mono}>{resolution.resolved_action}</span> prevails, as{' '}
            {resolution.prevailing.function} proposed.
          </p>
          <p className="text-muted-foreground">Rationale: {resolution.rationale}</p>
          <EvidenceList evidence={resolution.evidence} sourceSystem={source} />
        </div>
      ))}
    </Section>
  );
}

export function DissentSection({ view }: { view: BriefView }) {
  const source = view.identity.sourceSystem;
  return (
    <Section id="brief-dissent" title="Recorded dissent">
      {view.dissent.length === 0 ? (
        <p className="text-sm text-muted-foreground">No position was overruled.</p>
      ) : (
        <ul className="space-y-2">
          {view.dissent.map((item, index) => (
            <PositionItem
              key={index}
              position={item.position}
              sourceSystem={source}
              lead={
                item.overruledBy === null ? undefined : (
                  <span className="text-muted-foreground">
                    Overruled by <span className={mono}>{item.overruledBy}</span>:{' '}
                  </span>
                )
              }
            />
          ))}
        </ul>
      )}
    </Section>
  );
}

function PolicySection({ view }: { view: BriefView }) {
  const source = view.identity.sourceSystem;
  return (
    <Section id="brief-policy" title="Policy and contract context">
      <Facts
        rows={[
          [
            'Cited spans',
            view.policy.quotes.length === 0 ? (
              'none'
            ) : (
              <ul key="q">
                {view.policy.quotes.map((span) => (
                  <li key={span.target}>
                    <span className={mono}>{span.target}</span>,{' '}
                    <DocumentSpanLink
                      documentId={span.citation.document_id}
                      start={span.citation.start}
                      end={span.citation.end}
                      sourceSystem={source}
                    />
                  </li>
                ))}
              </ul>
            ),
          ],
          [
            'Contract documents (S14)',
            <RecordLinks
              key="c"
              entity="documents"
              ids={view.policy.contractDocumentIds}
              sourceSystem={source}
            />,
          ],
        ]}
      />
    </Section>
  );
}

function BacklogSection({ view }: { view: BriefView }) {
  return (
    <Section id="brief-backlog" title="Chronic backlog">
      <p className="text-sm">
        Chronic backlog tickets:{' '}
        <RecordLinks
          entity="support_tickets"
          ids={view.backlogTicketIds}
          sourceSystem={view.identity.sourceSystem}
        />
      </p>
      <p className="text-xs text-muted-foreground">
        A chronic backlog ticket is reported here and never drives the band.
      </p>
    </Section>
  );
}

function ActionsSection({ view }: { view: BriefView }) {
  return (
    <Section id="brief-actions" title="Recommended actions">
      {view.actions.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No action is recommended, because no function stated a position.
        </p>
      ) : (
        <ol className="space-y-2">
          {view.actions.map((position, index) => (
            <PositionItem
              key={index}
              position={position}
              sourceSystem={view.identity.sourceSystem}
            />
          ))}
        </ol>
      )}
    </Section>
  );
}

function EscalationSection({ view }: { view: BriefView }) {
  const path = view.escalation;
  const source = view.identity.sourceSystem;
  const ref = (item: { entity: string; id: string } | null) =>
    item === null ? (
      'none stated'
    ) : (
      <RecordLink entity={item.entity} id={item.id} sourceSystem={source} />
    );
  const refs = (items: readonly { entity: string; id: string }[]) =>
    items.length === 0 ? (
      'none'
    ) : (
      <span className="inline-flex flex-wrap gap-x-2">
        {items.map((item) => (
          <RecordLink key={item.id} entity={item.entity} id={item.id} sourceSystem={source} />
        ))}
      </span>
    );
  return (
    <Section id="brief-escalation" title="Escalation path">
      <Facts
        rows={[
          ['Account owner', ref(path.account_owner)],
          ["Account owner's manager", ref(path.account_owner_manager)],
          ['Open tickets', refs(path.open_tickets)],
          ['Assignees of open tickets', refs(path.assignees)],
          ["Assignees' managers", refs(path.assignee_managers)],
        ]}
      />
      <table className="w-full text-xs">
        <caption className="text-left text-sm font-semibold">Edges</caption>
        <thead className="text-left text-muted-foreground">
          <tr>
            <th scope="col" className="pr-2 font-normal">
              Edge
            </th>
            <th scope="col" className="pr-2 font-normal">
              From
            </th>
            <th scope="col" className="pr-2 font-normal">
              To
            </th>
            <th scope="col" className="font-normal">
              Basis
            </th>
          </tr>
        </thead>
        <tbody className="font-mono wrap-anywhere">
          {path.edges.map((edge, index) => (
            <tr key={index} className="border-t">
              <td className="pr-2">{edge.edge}</td>
              <td className="pr-2">{edge.source.id}</td>
              <td className="pr-2">{edge.target.id}</td>
              <td>
                {edge.basis}, {edge.carrier_field}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

function NarrativeSection({ view }: { view: BriefView }) {
  return (
    <Section id="brief-narrative" title="Narrative">
      <p className="text-xs text-muted-foreground">
        The stored text, exactly as the brief writer rendered it. An approval binds to the payload
        hash, not to this text.
      </p>
      <pre className="rounded-lg border bg-muted/40 p-3 font-mono text-xs break-words whitespace-pre-wrap">
        {view.narrative}
      </pre>
    </Section>
  );
}

function TechnicalSection({ view }: { view: BriefView }) {
  const technical = view.technical;
  return (
    <Section id="brief-technical" title="Technical">
      <Facts
        rows={[
          [
            'Brief id',
            <span key="b" className={mono}>
              {technical.briefId}
            </span>,
          ],
          [
            'Assessment id',
            <span key="a" className={mono}>
              {technical.assessmentId}
            </span>,
          ],
          [
            'Stored status',
            <span key="s" className={mono}>
              {technical.status}
            </span>,
          ],
          ['Policy version', String(technical.policyVersion)],
          [
            'Template version',
            <span key="t" className={mono}>
              {technical.templateVersion}
            </span>,
          ],
          [
            'Payload hash',
            <span key="h" className={`${mono} break-all`}>
              {technical.payloadHash}
            </span>,
          ],
          ['Citations', String(technical.citationCount)],
        ]}
      />
    </Section>
  );
}

function BriefSections({ view, customerName }: { view: BriefView; customerName: string | null }) {
  return (
    <div className="space-y-4">
      <IdentitySection view={view} name={customerName} />
      <RiskSection view={view} />
      <SignalsSection view={view} />
      <EvidenceSections view={view} customerName={customerName} />
      <CommercialSection view={view} />
      <ConflictSection view={view} />
      <DissentSection view={view} />
      <PolicySection view={view} />
      <BacklogSection view={view} />
      <ActionsSection view={view} />
      <EscalationSection view={view} />
      <NarrativeSection view={view} />
      <TechnicalSection view={view} />
    </div>
  );
}

function NotFound({ inboxHref }: { inboxHref: To }) {
  return (
    <div className="space-y-3">
      <EmptyState message="No brief exists at this address." art="desk" />
      <Link className="text-sm underline" to={inboxHref}>
        Return to the inbox
      </Link>
    </div>
  );
}

function Loaded({
  brief,
  decisions,
  customerName,
  inboxHref,
}: {
  brief: Brief;
  decisions: UseQueryResult<Fetched<DecisionResponse[]>>;
  customerName: string | null;
  inboxHref: To;
}) {
  const response = brief.response;
  if (!brief.supported) {
    return (
      <div className="space-y-3">
        <h1 className="text-xl font-semibold">Brief</h1>
        <EmptyState message={fill(COPY.unsupportedBrief, { n: brief.payloadVersion })} />
      </div>
    );
  }
  const view = buildBriefView(response, brief.payload);
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0 space-y-4">
        <header className="space-y-2">
          <h1 className="text-xl font-semibold">
            {customerName ?? view.identity.customerId}{' '}
            <span className="font-mono text-base text-muted-foreground">
              {view.identity.customerId}
            </span>
          </h1>
          <p className="flex flex-wrap items-center gap-2">
            <BandChip band={view.risk.band} />
            {view.risk.worthiness.executive_worthy && <ExecutiveBadge />}
            <DecisionStatusChip status={response.decision_status} />
            <span className="font-mono text-xs text-muted-foreground">
              as_of {view.identity.asOf}
            </span>
          </p>
        </header>
        <BriefSections view={view} customerName={customerName} />
      </div>
      <aside aria-label="Decision" className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <Card aria-labelledby="decision-title" className="space-y-3">
          <CardTitle id="decision-title">Your decision</CardTitle>
          <DecisionPanel
            key={response.id}
            briefId={response.id}
            payloadHash={response.payload_hash}
            chain={decisions.data?.data}
            inboxHref={inboxHref}
          />
        </Card>
        <Card aria-labelledby="chain-title" className="space-y-3">
          <CardTitle id="chain-title">Decision chain</CardTitle>
          <DecisionChain query={decisions} />
        </Card>
      </aside>
    </div>
  );
}

/** One brief with its decision panel and chain, and the requests behind them. */
export function BriefDetail({ briefId, inboxHref }: { briefId: string; inboxHref: To }) {
  const brief = useQuery(briefQuery(briefId));
  const decisions = useQuery(decisionsQuery(briefId));
  const customers = useQuery(entitiesQuery('customers'));
  const selectBrief = useSession((state) => state.selectBrief);
  useEffect(() => selectBrief(briefId), [briefId, selectBrief]);

  const calls = [
    ...(brief.data?.calls ?? []),
    ...(decisions.data?.calls ?? []),
    ...(customers.data?.calls ?? []),
  ];
  const heading = <h1 className="text-xl font-semibold">Brief</h1>;
  let body: ReactNode;
  if (brief.isPending) {
    body = (
      <>
        {heading}
        <LoadingState label="the brief" lines={6} />
      </>
    );
  } else if (brief.isError) {
    body = (
      <>
        {heading}
        {brief.error instanceof ApiError && brief.error.status === 404 ? (
          <NotFound inboxHref={inboxHref} />
        ) : (
          <ErrorState error={brief.error} onRetry={() => void brief.refetch()} />
        )}
      </>
    );
  } else {
    const payload = brief.data.data.supported ? brief.data.data.payload : null;
    const names = customers.data === undefined ? null : customerNames(customers.data.data);
    const customerName =
      payload === null || names === null
        ? null
        : (names.get(customerKey(payload.scope.source_system, payload.customer.id)) ?? null);
    body = (
      <Loaded
        brief={brief.data.data}
        decisions={decisions}
        customerName={customerName}
        inboxHref={inboxHref}
      />
    );
  }
  return (
    <div className="space-y-4">
      {body}
      <ApiXray calls={calls} />
    </div>
  );
}
