/**
 * The decision panel (spec §7.5, §7.6, §8.5, D-F-7): Approve or Reject the whole brief, with a
 * note and the decider's name.
 *
 * The request supersedes the chain's head. A refusal keeps the chosen decision and the typed note.
 * A request that never produced an answer has an unknown outcome: the page re-reads the chain and
 * offers a retry only when the decision is not in it (R-F-7). Nothing is retried automatically.
 * A recorded decision lands its stamp on the office's CEO desk (§9.5).
 */

import { useQueryClient } from '@tanstack/react-query';
import { RotateCw, Stamp } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { Link, type To } from 'react-router';

import { invalidateAfterDecision, queryKeys } from '@/api/queries';
import { fetchDecisions, recordDecision } from '@/api/risk';
import type { DecisionRequest, DecisionResponse } from '@/api/schemas/risk';
import { COPY } from '@/copy';
import {
  MAX_NOTE_CODE_POINTS,
  buildDecisionRequest,
  chainHead,
  codePointLength,
  decisionLanded,
  type DecisionChoice,
  type DecisionForm,
} from '@/domain/decisionChain';
import {
  classifyWriteFailure,
  failureRequestId,
  OUTCOME_MESSAGES,
  type WriteFailure,
} from '@/domain/outcomes';
import { readStored, STORAGE_KEYS, writeStored } from '@/lib/storage';
import { useDirector } from '@/state/director';
import { useSession } from '@/state/session';
import { ErrorState } from '@/states/states';
import { Button } from '@/ui/button';

type Phase =
  | { kind: 'editing' }
  | { kind: 'sending' }
  | { kind: 'recorded'; decision: DecisionResponse }
  | { kind: 'failed'; failure: WriteFailure }
  | { kind: 'checking' }
  | { kind: 'checked'; landed: boolean; moved: boolean }
  | { kind: 'check-failed'; error: unknown; sent: DecisionRequest };

function RequestId({ id }: { id: string | null }) {
  return <span className="font-mono text-xs text-muted-foreground">request {id ?? 'none'}</span>;
}

function Outcome({
  phase,
  onRetry,
  onCheckAgain,
  inboxHref,
}: {
  phase: Phase;
  onRetry: () => void;
  onCheckAgain: () => void;
  inboxHref: To;
}) {
  const retry = (
    <Button type="button" variant="outline" size="sm" onClick={onRetry}>
      <RotateCw aria-hidden="true" />
      Retry
    </Button>
  );
  switch (phase.kind) {
    case 'editing':
    case 'sending':
      return null;
    case 'recorded':
      return (
        <p role="status" className="text-sm">
          Recorded: {phase.decision.decision} by {phase.decision.actor}. It is now the chain&apos;s
          head.
        </p>
      );
    case 'checking':
      return (
        <p role="status" className="text-sm">
          {COPY.unknownOutcome}
        </p>
      );
    case 'checked':
      if (phase.landed) {
        return (
          <p role="status" className="text-sm">
            It was recorded. The chain below includes it.
          </p>
        );
      }
      return (
        <div role="alert" className="space-y-2 text-sm">
          <p>
            {phase.moved
              ? OUTCOME_MESSAGES.staleHead
              : 'It was not recorded, so you can send it again.'}
          </p>
          {retry}
        </div>
      );
    case 'check-failed':
      return (
        <div role="alert" className="space-y-2 text-sm">
          <p>The check could not reach the API, so the result is still unknown.</p>
          <ErrorState error={phase.error} />
          <Button type="button" variant="outline" size="sm" onClick={onCheckAgain}>
            <RotateCw aria-hidden="true" />
            Check again
          </Button>
        </div>
      );
    case 'failed': {
      const { failure } = phase;
      const requestId = failureRequestId(failure);
      switch (failure.kind) {
        case 'stale-head':
          return (
            <div role="alert" className="space-y-1 text-sm">
              <p>{OUTCOME_MESSAGES.staleHead}</p>
              <p className="text-muted-foreground">
                The chain is reloaded. Your decision and note are kept: send them again to decide on
                the new head.
              </p>
            </div>
          );
        case 'defect':
          return (
            <div role="alert" className="space-y-1 text-sm">
              <p>{OUTCOME_MESSAGES.defect}</p>
              <RequestId id={requestId} />
            </div>
          );
        case 'brief-changed':
          return (
            <div role="alert" className="space-y-1 text-sm">
              <p>{OUTCOME_MESSAGES.briefChanged}</p>
              <p className="text-muted-foreground">The brief is reloaded. Your note is kept.</p>
            </div>
          );
        case 'payload-mismatch':
          return null;
        case 'invalid':
          return (
            <div role="alert" className="space-y-1 text-sm">
              <p>{OUTCOME_MESSAGES.invalid}</p>
              <ul className="list-disc pl-5 font-mono text-xs">
                {failure.fields.map((field) => (
                  <li key={field}>{field}</li>
                ))}
              </ul>
            </div>
          );
        case 'not-found':
          return (
            <div role="alert" className="space-y-1 text-sm">
              <p>This brief does not exist, so no decision can be recorded on it.</p>
              <Link className="underline" to={inboxHref}>
                Return to the inbox
              </Link>
            </div>
          );
        case 'nothing-written':
          return (
            <div role="alert" className="flex flex-wrap items-center gap-3 text-sm">
              <p>{OUTCOME_MESSAGES.nothingWritten}</p>
              <RequestId id={requestId} />
              {retry}
            </div>
          );
        case 'unknown':
        case 'unreadable':
          return <ErrorState error={failure.error} />;
      }
    }
  }
}

const CHOICES: readonly { value: DecisionChoice; label: string }[] = [
  { value: 'APPROVED', label: 'Approve' },
  { value: 'REJECTED', label: 'Reject' },
];

export function DecisionPanel({
  briefId,
  payloadHash,
  chain,
  inboxHref,
}: {
  briefId: string;
  payloadHash: string;
  /** The loaded chain; undefined while it loads or when it failed. */
  chain: readonly DecisionResponse[] | undefined;
  inboxHref: To;
}) {
  const client = useQueryClient();
  const refused = useSession((state) => briefId in state.refusedBriefs);
  const refusalRequestId = useSession((state) => state.refusedBriefs[briefId] ?? null);
  const refuseBrief = useSession((state) => state.refuseBrief);
  const stampDecision = useDirector((state) => state.stampDecision);
  const [form, setForm] = useState<DecisionForm>(() => ({
    actor: readStored(STORAGE_KEYS.actorName) ?? '',
    decision: null,
    note: '',
  }));
  const [phase, setPhase] = useState<Phase>({ kind: 'editing' });
  const ids = { note: useId(), actor: useId(), noteCount: useId() };

  const check = chain === undefined ? null : buildDecisionRequest(form, payloadHash, chain);
  const busy = phase.kind === 'sending' || phase.kind === 'checking';
  // The name may be remembered from an earlier visit, so only a chosen decision or a typed note
  // counts as the user having started this form.
  const touched = form.decision !== null || form.note !== '';

  async function recheck(sent: DecisionRequest) {
    setPhase({ kind: 'checking' });
    try {
      const reread = (await fetchDecisions(briefId)).data.items;
      const landed = decisionLanded(reread, sent) !== null;
      if (landed) stampDecision(sent.decision);
      const moved = !landed && (chainHead(reread)?.id ?? null) !== sent.supersedes_id;
      setPhase({ kind: 'checked', landed, moved });
      if (landed) setForm((current) => ({ ...current, decision: null, note: '' }));
      await invalidateAfterDecision(client, briefId);
    } catch (error) {
      setPhase({ kind: 'check-failed', error, sent });
    }
  }

  async function submit() {
    if (check === null || !check.ok) return;
    const sent = check.request;
    setPhase({ kind: 'sending' });
    writeStored(STORAGE_KEYS.actorName, sent.actor);
    try {
      const result = await recordDecision(briefId, sent);
      setPhase({ kind: 'recorded', decision: result.data });
      stampDecision(result.data.decision);
      setForm((current) => ({ ...current, decision: null, note: '' }));
      await invalidateAfterDecision(client, briefId);
      return;
    } catch (error) {
      const failure = classifyWriteFailure(error);
      if (failure.kind === 'unknown') {
        await recheck(sent);
        return;
      }
      setPhase({ kind: 'failed', failure });
      if (failure.kind === 'payload-mismatch') refuseBrief(briefId, failureRequestId(failure));
      if (failure.kind === 'stale-head' || failure.kind === 'defect') {
        await invalidateAfterDecision(client, briefId);
      }
      if (failure.kind === 'brief-changed') {
        await client.invalidateQueries({ queryKey: queryKeys.brief(briefId) });
      }
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void submit();
  }

  const noteLength = codePointLength(form.note.trim());
  return (
    <form onSubmit={onSubmit} aria-label="Record a decision" className="space-y-3">
      {refused && (
        <div role="alert" className="space-y-1 rounded-lg border border-bad/40 p-3 text-sm">
          <p>{OUTCOME_MESSAGES.payloadMismatch}</p>
          <RequestId id={refusalRequestId} />
        </div>
      )}
      <fieldset disabled={refused || busy} className="space-y-3">
        <fieldset className="flex gap-2">
          <legend className="sr-only">Decision</legend>
          {CHOICES.map((choice) => (
            <label
              key={choice.value}
              className="flex flex-1 cursor-pointer items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-medium has-[:checked]:border-primary has-[:checked]:bg-primary has-[:checked]:text-primary-foreground has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring"
            >
              <input
                type="radio"
                name={`decision-${briefId}`}
                value={choice.value}
                checked={form.decision === choice.value}
                onChange={() => setForm((current) => ({ ...current, decision: choice.value }))}
                className="sr-only"
              />
              {choice.label}
            </label>
          ))}
        </fieldset>
        <div className="space-y-1">
          <label htmlFor={ids.note} className="text-sm font-medium">
            Note <span className="font-normal text-muted-foreground">(optional)</span>
          </label>
          <textarea
            id={ids.note}
            rows={3}
            value={form.note}
            onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}
            aria-describedby={ids.noteCount}
            className="w-full rounded-md border bg-card px-2 py-1.5 text-sm"
          />
          <p id={ids.noteCount} className="text-xs text-muted-foreground">
            {noteLength} of {MAX_NOTE_CODE_POINTS} characters
          </p>
        </div>
        <div className="space-y-1">
          <label htmlFor={ids.actor} className="text-sm font-medium">
            Your name
          </label>
          <input
            id={ids.actor}
            value={form.actor}
            autoComplete="name"
            onChange={(event) => setForm((current) => ({ ...current, actor: event.target.value }))}
            className="h-9 w-full rounded-md border bg-card px-2 text-sm"
          />
          <p className="text-xs text-muted-foreground">Remembered in this browser only.</p>
        </div>
      </fieldset>
      <p className="text-xs font-medium">{COPY.decisionDisclaimer}</p>
      {touched && check !== null && !check.ok && (
        <ul className="list-disc pl-5 text-xs text-muted-foreground">
          {check.problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
      <Button
        type="submit"
        disabled={refused || busy || check === null || !check.ok}
        className="w-full"
      >
        <Stamp aria-hidden="true" />
        {phase.kind === 'sending' ? 'Recording…' : 'Record decision'}
      </Button>
      <Outcome
        phase={phase}
        onRetry={() => void submit()}
        onCheckAgain={() => {
          if (phase.kind === 'check-failed') void recheck(phase.sent);
        }}
        inboxHref={inboxHref}
      />
    </form>
  );
}
