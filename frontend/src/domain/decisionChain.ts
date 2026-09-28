/**
 * The decision chain and the decision request (spec §7.5; DERIVED from `app/decisions/approval.py`
 * and `DecisionRequest` in `app/api/v1/schemas.py`).
 *
 * The chain is `GET …/decisions` `items`, first to head. A new decision supersedes the head, or
 * nothing when the chain is empty. The actor is 1–255 characters and the note at most 2000, both
 * counted as Python counts them: in code points.
 */

import type { DecisionRequest, DecisionResponse } from '@/api/schemas/risk';

export const MAX_ACTOR_CODE_POINTS = 255;
export const MAX_NOTE_CODE_POINTS = 2000;

export type DecisionChoice = DecisionRequest['decision'];

const CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳';

/** ①, ②, … ⑳, then (21), (22), … */
export function ordinalMark(ordinal: number): string {
  return Array.from(CIRCLED)[ordinal - 1] ?? `(${ordinal})`;
}

export function codePointLength(text: string): number {
  return Array.from(text).length;
}

export interface ChainEntry {
  decision: DecisionResponse;
  ordinal: number;
  mark: string;
  /** The entry this one superseded, when it is in the chain. */
  supersedes: { id: string; mark: string } | null;
}

/** The chain as numbered entries, first to head. */
export function chainEntries(items: readonly DecisionResponse[]): ChainEntry[] {
  const marks = new Map(items.map((item, index) => [item.id, ordinalMark(index + 1)]));
  return items.map((decision, index) => {
    const supersededMark =
      decision.supersedes_id === null ? undefined : marks.get(decision.supersedes_id);
    return {
      decision,
      ordinal: index + 1,
      mark: ordinalMark(index + 1),
      supersedes:
        decision.supersedes_id === null || supersededMark === undefined
          ? null
          : { id: decision.supersedes_id, mark: supersededMark },
    };
  });
}

/** The head: the chain's last decision, or null for an empty chain. */
export function chainHead(items: readonly DecisionResponse[]): DecisionResponse | null {
  return items.at(-1) ?? null;
}

export interface DecisionForm {
  actor: string;
  decision: DecisionChoice | null;
  note: string;
}

export type FormCheck = { ok: true; request: DecisionRequest } | { ok: false; problems: string[] };

/** The request the form states, or what stops it from being sent. */
export function buildDecisionRequest(
  form: DecisionForm,
  payloadHash: string,
  chain: readonly DecisionResponse[],
): FormCheck {
  const actor = form.actor.trim();
  const note = form.note.trim();
  const problems: string[] = [];
  if (form.decision === null) problems.push('Choose Approve or Reject.');
  if (actor === '') problems.push('Enter your name.');
  if (codePointLength(actor) > MAX_ACTOR_CODE_POINTS) {
    problems.push(`Your name is longer than ${MAX_ACTOR_CODE_POINTS} characters.`);
  }
  if (codePointLength(note) > MAX_NOTE_CODE_POINTS) {
    problems.push(`The note is longer than ${MAX_NOTE_CODE_POINTS} characters.`);
  }
  if (form.decision === null || problems.length > 0) return { ok: false, problems };
  return {
    ok: true,
    request: {
      actor,
      decision: form.decision,
      note: note === '' ? null : note,
      payload_hash: payloadHash,
      supersedes_id: chainHead(chain)?.id ?? null,
    },
  };
}

/** Whether a re-read chain holds the decision that was sent (R-F-7). */
export function decisionLanded(
  chain: readonly DecisionResponse[],
  sent: DecisionRequest,
): DecisionResponse | null {
  return (
    chain.find(
      (item) =>
        item.supersedes_id === sent.supersedes_id &&
        item.actor === sent.actor &&
        item.decision === sent.decision &&
        item.note === sent.note &&
        item.payload_hash === sent.payload_hash,
    ) ?? null
  );
}
