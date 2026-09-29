/**
 * Evidence links (spec §8.4): every evidence item opens what it cites. A record citation or an
 * entity reference opens the Layer 1 record, built from its entity list; a document citation opens
 * the document's citable text with the span marked. The dialogs trap focus and return it (§10).
 * Over the office, opening a ticket highlights SUPPORT_AGENT's desk and opening a document
 * highlights LINKER_AGENT's.
 */

import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { Dialog } from 'radix-ui';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router';

import { entitiesQuery } from '@/api/queries';
import type { Citation, Evidence } from '@/api/schemas/briefPayloadV1';
import { entityTypeOf, findRecord, recordFields } from '@/domain/records';
import { evidenceDesk } from '@/domain/roster';
import { viewOf } from '@/domain/views';
import { citableText, highlight, spanFits } from '@/domain/spans';
import { cn } from '@/lib/utils';
import { useSession } from '@/state/session';
import { EmptyState, ErrorState, LoadingState } from '@/states/states';
import { Button } from '@/ui/button';

const linkButton =
  'rounded-sm font-mono text-xs text-primary underline decoration-dotted underline-offset-2 hover:decoration-solid';

function EvidenceDialog({
  entity,
  label,
  title,
  description,
  children,
}: {
  /** The entity type the dialog opens, which picks the desk to highlight. */
  entity: string;
  label: ReactNode;
  title: string;
  description: string;
  children: ReactNode;
}) {
  const { pathname } = useLocation();
  const highlight = useSession((state) => state.highlight);
  const desk = evidenceDesk(entity);
  return (
    <Dialog.Root
      onOpenChange={(open) => {
        if (open && desk !== null && viewOf(pathname) === 'office') highlight(desk);
      }}
    >
      <Dialog.Trigger className={linkButton}>{label}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[85vh] w-[min(44rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border bg-card p-5 text-foreground shadow-lg">
          <div className="mb-3 flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="font-mono text-base font-semibold">{title}</Dialog.Title>
              <Dialog.Description className="text-sm text-muted-foreground">
                {description}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="sm" aria-label="Close">
                <X aria-hidden="true" />
              </Button>
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function RecordBody({
  entity,
  id,
  field,
  sourceSystem,
}: {
  entity: string;
  id: string;
  field: string | null;
  sourceSystem: string;
}) {
  const type = entityTypeOf(entity);
  const query = useQuery({ ...entitiesQuery(type ?? 'customers'), enabled: type !== null });
  if (type === null) return <EmptyState message={`This frontend cannot open ${entity} records.`} />;
  if (query.isPending) return <LoadingState label={`${entity} ${id}`} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const record = findRecord(query.data.data, sourceSystem, id);
  if (record === null) {
    return (
      <EmptyState message={`No ${entity} record ${id} exists in Layer 1 for ${sourceSystem}.`} />
    );
  }
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      {recordFields(record).map((item) => (
        <div key={item.name} className="contents">
          <dt
            className={cn(
              'font-mono text-xs text-muted-foreground',
              item.name === field && 'font-semibold text-foreground',
            )}
          >
            {item.name}
            {item.name === field && ' (cited)'}
          </dt>
          <dd
            className={cn(
              'font-mono text-xs break-words whitespace-pre-wrap',
              item.name === field && 'rounded bg-band-watch/30 px-1',
            )}
          >
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** A Layer 1 record, opened from an entity reference or a record citation. */
export function RecordLink({
  entity,
  id,
  field = null,
  sourceSystem,
  children,
}: {
  entity: string;
  id: string;
  field?: string | null;
  sourceSystem: string;
  children?: ReactNode;
}) {
  return (
    <EvidenceDialog
      entity={entity}
      label={children ?? id}
      title={`${entity} ${id}`}
      description={
        field === null
          ? `The Layer 1 record, as GET /api/v1/entities/${entity} returns it.`
          : `The Layer 1 record; the cited field is ${field}.`
      }
    >
      <RecordBody entity={entity} id={id} field={field} sourceSystem={sourceSystem} />
    </EvidenceDialog>
  );
}

function DocumentSpanBody({
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
  const query = useQuery(entitiesQuery('documents'));
  if (query.isPending) return <LoadingState label={`document ${documentId}`} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const document = findRecord(query.data.data, sourceSystem, documentId);
  if (document === null) {
    return (
      <EmptyState message={`No document ${documentId} exists in Layer 1 for ${sourceSystem}.`} />
    );
  }
  const text = citableText(document);
  if (!spanFits(text, start, end)) {
    return (
      <EmptyState
        message={`The span [${start}, ${end}) lies outside document ${documentId}'s text.`}
      />
    );
  }
  const parts = highlight(text, start, end);
  return (
    <p className="rounded-lg border bg-muted/40 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap">
      {parts.before}
      <mark className="rounded bg-band-watch/40 px-0.5 text-foreground">{parts.span}</mark>
      {parts.after}
    </p>
  );
}

/** A document span, opened on the document's citable text with the span marked. */
export function DocumentSpanLink({
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
  return (
    <EvidenceDialog
      entity="documents"
      label={`${documentId} [${start}, ${end})`}
      title={`${documentId} [${start}, ${end})`}
      description="The document's citable text (title, a line break, then the body) with the cited span marked."
    >
      <DocumentSpanBody
        documentId={documentId}
        start={start}
        end={end}
        sourceSystem={sourceSystem}
      />
    </EvidenceDialog>
  );
}

export function CitationLink({
  citation,
  sourceSystem,
}: {
  citation: Citation;
  sourceSystem: string;
}) {
  if (citation.kind === 'document') {
    return (
      <DocumentSpanLink
        documentId={citation.document_id}
        start={citation.start}
        end={citation.end}
        sourceSystem={sourceSystem}
      />
    );
  }
  return (
    <RecordLink
      entity={citation.entity}
      id={citation.id}
      field={citation.field}
      sourceSystem={sourceSystem}
    >
      {`${citation.entity} ${citation.id} ${citation.field}`}
    </RecordLink>
  );
}

/** An evidence list, each item linking to what it cites. */
export function EvidenceList({
  evidence,
  sourceSystem,
}: {
  evidence: readonly Evidence[];
  sourceSystem: string;
}) {
  if (evidence.length === 0) {
    return <p className="text-xs text-muted-foreground">No evidence stated.</p>;
  }
  return (
    <ul className="space-y-0.5 text-xs">
      {evidence.map((item, index) => (
        <li key={index} className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-mono text-muted-foreground">{item.kind}</span>
          <CitationLink citation={item.citation} sourceSystem={sourceSystem} />
          {item.rule_id !== undefined && (
            <span className="font-mono text-muted-foreground">rule {item.rule_id}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

/** A list of ids, each opening its record. */
export function RecordLinks({
  entity,
  ids,
  sourceSystem,
  empty = 'none',
}: {
  entity: string;
  ids: readonly string[];
  sourceSystem: string;
  empty?: string;
}) {
  if (ids.length === 0) return <span className="text-muted-foreground">{empty}</span>;
  return (
    <span className="inline-flex flex-wrap gap-x-2 gap-y-0.5">
      {ids.map((id) => (
        <RecordLink key={id} entity={entity} id={id} sourceSystem={sourceSystem} />
      ))}
    </span>
  );
}
