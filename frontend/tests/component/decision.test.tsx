/**
 * The decision panel and chain (spec §7.5, §7.6, §8.5, §8.6, AC-F-5, AC-F-6, R-F-7), against the
 * recorded decision flow: every §7.6 row renders its message and behaviour, and no typed note is
 * lost.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import type { DecisionResponse } from '@/api/schemas/risk';
import { COPY } from '@/copy';
import { OUTCOME_MESSAGES } from '@/domain/outcomes';
import { STORAGE_KEYS } from '@/lib/storage';
import { useSession } from '@/state/session';

import {
  answer,
  briefBodies,
  briefId,
  chainHandler,
  drop,
  hang,
  recordedApproval,
  recordedChain,
  recordedRefusal,
  recordedRejection,
  refuse,
} from '../support/api';
import type { RecordedExchange } from '../support/fixtures';
import { renderRoute } from '../support/render';
import { server } from '../support/server';

const recorded = (recordedChain().body as { items: DecisionResponse[] }).items;
const [firstDecision] = recorded as [DecisionResponse];
const payloadHash = briefBodies()[0]?.payload_hash ?? '';

interface Harness {
  sent: Record<string, unknown>[];
  chain: DecisionResponse[];
  chainReads: number;
  briefReads: number;
}

/**
 * Serve the CUST-007 brief's chain from `harness.chain` and answer each POST with the next of
 * `answers`. A 201 appends the decision it returns to the chain, as the API would.
 */
function serve(answers: (() => Response | Promise<Response>)[], chain: DecisionResponse[] = []) {
  const harness: Harness = { sent: [], chain: [...chain], chainReads: 0, briefReads: 0 };
  let next = 0;
  server.use(
    http.get(`*/api/v1/risk/briefs/${briefId(0)}/decisions`, () => {
      harness.chainReads += 1;
      return HttpResponse.json(
        { items: harness.chain },
        { headers: { 'X-Request-ID': 'rid-chain' } },
      );
    }),
    http.get(`*/api/v1/risk/briefs/${briefId(0)}`, () => {
      harness.briefReads += 1;
      return HttpResponse.json(briefBodies()[0], { headers: { 'X-Request-ID': 'rid-brief' } });
    }),
    http.post(`*/api/v1/risk/briefs/${briefId(0)}/decision`, async ({ request }) => {
      harness.sent.push((await request.json()) as Record<string, unknown>);
      const respond = answers[Math.min(next, answers.length - 1)];
      next += 1;
      const response = await (respond as () => Response | Promise<Response>)();
      if (response.status === 201) {
        harness.chain.push((await response.clone().json()) as DecisionResponse);
      }
      return response;
    }),
  );
  return harness;
}

const recordedAnswer = (exchange: RecordedExchange) => () => answer(exchange, 'rid-post');

async function openForm() {
  renderRoute(`/classic/briefs/${briefId(0)}?as_of=2026-09-18`);
  const form = await screen.findByRole('form', { name: 'Record a decision' });
  await screen.findByRole('region', { name: 'Decision chain' });
  return form;
}

async function fill(form: HTMLElement, choice: 'Approve' | 'Reject', note: string, name = 'Owner') {
  await userEvent.click(within(form).getByRole('radio', { name: choice }));
  const noteField = within(form).getByLabelText(/^Note/);
  await userEvent.clear(noteField);
  if (note !== '') await userEvent.type(noteField, note);
  const nameField = within(form).getByLabelText('Your name');
  await userEvent.clear(nameField);
  await userEvent.type(nameField, name);
}

function submit(form: HTMLElement) {
  return userEvent.click(within(form).getByRole('button', { name: 'Record decision' }));
}

function chainRegion() {
  return screen.getByRole('region', { name: 'Decision chain' });
}

describe('an empty chain and the form', () => {
  it('shows the empty chain, the fixed identity line, and a disabled button until valid', async () => {
    serve([recordedAnswer(recordedApproval())]);
    const form = await openForm();

    expect(await within(chainRegion()).findByText(COPY.emptyDecisionChain)).toBeInTheDocument();
    expect(within(form).getByText(COPY.decisionDisclaimer)).toBeInTheDocument();
    const button = within(form).getByRole('button', { name: 'Record decision' });
    expect(button).toBeDisabled();

    await userEvent.click(within(form).getByRole('radio', { name: 'Approve' }));
    expect(within(form).getByText('Enter your name.')).toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText('Your name'), 'Owner');
    expect(button).toBeEnabled();
  });

  it('counts the note in characters of the 2000 allowed', async () => {
    serve([]);
    const form = await openForm();

    await userEvent.type(within(form).getByLabelText(/^Note/), 'Hi 😀');
    expect(within(form).getByText('4 of 2000 characters')).toBeInTheDocument();
  });

  it('remembers the name in this browser', async () => {
    window.localStorage.setItem(STORAGE_KEYS.actorName, 'Remembered');
    serve([]);
    const form = await openForm();
    expect(within(form).getByLabelText('Your name')).toHaveValue('Remembered');
  });

  it('works the same when browser storage is unavailable (§11)', async () => {
    const denied = () => {
      throw new DOMException('denied', 'SecurityError');
    };
    const read = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(denied);
    const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(denied);
    try {
      serve([recordedAnswer(recordedApproval())]);
      const form = await openForm();
      expect(within(form).getByLabelText('Your name')).toHaveValue('');

      await fill(form, 'Approve', 'no storage');
      await submit(form);
      expect(await within(form).findByText(/^Recorded: APPROVED/)).toBeInTheDocument();
      expect(write).toHaveBeenCalled();
    } finally {
      read.mockRestore();
      write.mockRestore();
    }
  });
});

describe('recording decisions (AC-F-5)', () => {
  it('approves: supersedes nothing, then the chain and the status update', async () => {
    const harness = serve([recordedAnswer(recordedApproval())]);
    const form = await openForm();

    await fill(form, 'Approve', '  Recorded by the fixture tool.  ', '  Fixture Recorder ');
    await submit(form);

    expect(
      await within(form).findByText(/^Recorded: APPROVED by Fixture Recorder/),
    ).toBeInTheDocument();
    expect(harness.sent).toEqual([
      {
        actor: 'Fixture Recorder',
        decision: 'APPROVED',
        note: 'Recorded by the fixture tool.',
        payload_hash: payloadHash,
        supersedes_id: null,
      },
    ]);
    const chain = chainRegion();
    expect(await within(chain).findByText('APPROVED')).toBeInTheDocument();
    expect(within(chain).getByText('①')).toBeInTheDocument();
    expect(within(chain).getByText(`hash ${payloadHash.slice(0, 12)}`)).toHaveAttribute(
      'title',
      payloadHash,
    );
    expect(within(form).getByLabelText(/^Note/)).toHaveValue('');
    expect(window.localStorage.getItem(STORAGE_KEYS.actorName)).toBe('Fixture Recorder');
  });

  it('rejects with supersede: the request names the head, and ② supersedes ①', async () => {
    const harness = serve([recordedAnswer(recordedRejection())], [firstDecision]);
    const form = await openForm();
    await within(chainRegion()).findByText('①');

    await fill(form, 'Reject', 'Superseded by the fixture tool.', 'Fixture Recorder');
    await submit(form);

    await within(chainRegion()).findByText('②');
    expect(harness.sent[0]).toMatchObject({
      decision: 'REJECTED',
      supersedes_id: firstDecision.id,
    });
    const link = within(chainRegion()).getByRole('link', { name: 'supersedes ①' });
    expect(link).toHaveAttribute('href', `#decision-${firstDecision.id}`);
  });

  it('sends an empty note as null', async () => {
    const harness = serve([recordedAnswer(recordedApproval())]);
    const form = await openForm();

    await fill(form, 'Approve', '');
    await submit(form);

    await within(form).findByText(/^Recorded:/);
    expect(harness.sent[0]?.note).toBeNull();
  });

  it('disables the form while the request is in flight', async () => {
    serve([hang]);
    const form = await openForm();

    await fill(form, 'Approve', 'wait');
    await submit(form);

    expect(await within(form).findByRole('button', { name: 'Recording…' })).toBeDisabled();
    expect(within(form).getByLabelText(/^Note/)).toBeDisabled();
  });
});

describe('every refusal of §7.6 (AC-F-6)', () => {
  it('409 SUPERSEDES_REQUIRED, as recorded: someone decided meanwhile; the chain reloads', async () => {
    const harness = serve([
      recordedAnswer(recordedRefusal('SUPERSEDES_REQUIRED')),
      recordedAnswer(recordedRejection()),
    ]);
    const form = await openForm();
    const readsBefore = harness.chainReads;

    await fill(form, 'Reject', 'keep this note');
    harness.chain.push(firstDecision);
    await submit(form);

    expect(await within(form).findByText(OUTCOME_MESSAGES.staleHead)).toBeInTheDocument();
    await waitFor(() => expect(harness.chainReads).toBeGreaterThan(readsBefore));
    expect(within(form).getByLabelText(/^Note/)).toHaveValue('keep this note');
    expect(within(form).getByRole('radio', { name: 'Reject' })).toBeChecked();

    await within(chainRegion()).findByText('①');
    await submit(form);
    await within(form).findByText(/^Recorded: REJECTED/);
    expect(harness.sent[1]).toMatchObject({
      supersedes_id: firstDecision.id,
      note: 'keep this note',
    });
  });

  it('409 PREDECESSOR_NOT_HEAD, as recorded: the same message and behaviour', async () => {
    serve([recordedAnswer(recordedRefusal('PREDECESSOR_NOT_HEAD'))]);
    const form = await openForm();

    await fill(form, 'Approve', 'note');
    await submit(form);

    expect(await within(form).findByText(OUTCOME_MESSAGES.staleHead)).toBeInTheDocument();
  });

  it('409 PREDECESSOR_NOT_ON_BRIEF, as recorded: the defect message and the request id', async () => {
    const refusal = recordedRefusal('PREDECESSOR_NOT_ON_BRIEF');
    serve([recordedAnswer(refusal)]);
    const form = await openForm();

    await fill(form, 'Approve', 'note');
    await submit(form);

    expect(await within(form).findByText(OUTCOME_MESSAGES.defect)).toBeInTheDocument();
    // The X-Request-ID header is the id shown; the API sends the same id in the body.
    expect(within(form).getByText('request rid-post')).toBeInTheDocument();
  });

  it('409 REQUEST_HASH_MISMATCH, as recorded: the brief changed; it reloads; the note stays', async () => {
    const harness = serve([recordedAnswer(recordedRefusal('REQUEST_HASH_MISMATCH'))]);
    const form = await openForm();
    const readsBefore = harness.briefReads;

    await fill(form, 'Approve', 'my careful note');
    await submit(form);

    expect(await within(form).findByText(OUTCOME_MESSAGES.briefChanged)).toBeInTheDocument();
    await waitFor(() => expect(harness.briefReads).toBeGreaterThan(readsBefore));
    expect(within(form).getByLabelText(/^Note/)).toHaveValue('my careful note');
  });

  it('409 STORED_PAYLOAD_MISMATCH: decisions on this brief are refused, with the request id', async () => {
    const recordedHash = recordedRefusal('REQUEST_HASH_MISMATCH');
    const body = recordedHash.body as { error: Record<string, unknown> };
    serve([
      () =>
        HttpResponse.json(
          {
            error: {
              ...body.error,
              details: { reason: 'STORED_PAYLOAD_MISMATCH' },
              request_id: 'rid-stored',
            },
          },
          { status: 409, headers: { 'X-Request-ID': 'rid-stored' } },
        ),
    ]);
    const form = await openForm();

    await fill(form, 'Approve', 'note');
    await submit(form);

    expect(await within(form).findByText(OUTCOME_MESSAGES.payloadMismatch)).toBeInTheDocument();
    expect(within(form).getByText('request rid-stored')).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: 'Record decision' })).toBeDisabled();
    expect(within(form).getByLabelText(/^Note/)).toBeDisabled();
    expect(useSession.getState().refusedBriefs).toEqual({ [briefId(0)]: 'rid-stored' });
  });

  it('422 INVALID_REQUEST, as recorded: the field messages', async () => {
    serve([recordedAnswer(recordedRefusal('INVALID_REQUEST'))]);
    const form = await openForm();

    await fill(form, 'Approve', 'note');
    await submit(form);

    expect(await within(form).findByText(OUTCOME_MESSAGES.invalid)).toBeInTheDocument();
    expect(
      within(form).getByText('body.actor: String should have at least 1 character'),
    ).toBeInTheDocument();
  });

  it('404: the brief does not exist, with a way back to the inbox', async () => {
    serve([() => refuse(404, 'BRIEF_NOT_FOUND')]);
    const form = await openForm();

    await fill(form, 'Approve', 'note');
    await submit(form);

    expect(
      await within(form).findByText(
        'This brief does not exist, so no decision can be recorded on it.',
      ),
    ).toBeInTheDocument();
    expect(within(form).getByRole('link', { name: 'Return to the inbox' })).toHaveAttribute(
      'href',
      '/classic/inbox?as_of=2026-09-18',
    );
  });

  it('500: nothing was written, with the request id; Retry sends it again', async () => {
    const harness = serve([
      () => refuse(500, 'INTERNAL_ERROR', null, 'rid-500'),
      recordedAnswer(recordedApproval()),
    ]);
    const form = await openForm();

    await fill(form, 'Approve', 'note');
    await submit(form);

    expect(await within(form).findByText(OUTCOME_MESSAGES.nothingWritten)).toBeInTheDocument();
    expect(within(form).getByText('request rid-500')).toBeInTheDocument();
    await userEvent.click(within(form).getByRole('button', { name: 'Retry' }));
    await within(form).findByText(/^Recorded: APPROVED/);
    expect(harness.sent).toHaveLength(2);
  });

  it('a 2xx body the frontend cannot read: the error state', async () => {
    serve([() => HttpResponse.json({ nope: true }, { status: 201 })]);
    const form = await openForm();

    await fill(form, 'Approve', 'note');
    await submit(form);

    expect(await within(form).findByRole('alert')).toHaveTextContent('CONTRACT_ERROR');
  });
});

describe('an unknown outcome is re-read first (R-F-7)', () => {
  it('the decision landed: it says so, and offers no retry', async () => {
    const approval = recordedApproval().body as DecisionResponse;
    const harness = serve([
      () => {
        harness.chain.push({ ...approval, actor: 'Owner', note: 'landed' });
        return HttpResponse.error();
      },
    ]);
    const form = await openForm();

    await fill(form, 'Approve', 'landed');
    await submit(form);

    expect(
      await within(form).findByText('It was recorded. The chain below includes it.'),
    ).toBeInTheDocument();
    expect(within(form).queryByRole('button', { name: 'Retry' })).toBeNull();
    expect(harness.sent).toHaveLength(1);
    expect(await within(chainRegion()).findByText('landed')).toBeInTheDocument();
  });

  it('the decision did not land: it offers a retry, which sends once more', async () => {
    const harness = serve([drop, recordedAnswer(recordedApproval())]);
    const form = await openForm();

    await fill(form, 'Approve', 'retry me');
    await submit(form);

    expect(
      await within(form).findByText('It was not recorded, so you can send it again.'),
    ).toBeInTheDocument();
    expect(harness.sent).toHaveLength(1);
    await userEvent.click(within(form).getByRole('button', { name: 'Retry' }));
    await within(form).findByText(/^Recorded:/);
    expect(harness.sent).toHaveLength(2);
  });

  it('someone else decided meanwhile: the stale-head message', async () => {
    const harness = serve([
      () => {
        harness.chain.push(firstDecision);
        return HttpResponse.error();
      },
    ]);
    const form = await openForm();

    await fill(form, 'Reject', 'mine');
    await submit(form);

    expect(await within(form).findByText(OUTCOME_MESSAGES.staleHead)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^Note/)).toHaveValue('mine');
  });

  it('shows the unknown-outcome message while it re-reads, and Check again when that fails', async () => {
    let reads = 0;
    const harness = serve([drop]);
    server.use(
      http.get(`*/api/v1/risk/briefs/${briefId(0)}/decisions`, () => {
        reads += 1;
        if (reads === 1) return HttpResponse.json({ items: [] });
        if (reads === 2) return refuse(404, 'BRIEF_NOT_FOUND', null, 'rid-reread');
        return HttpResponse.json({ items: harness.chain });
      }),
    );
    const form = await openForm();

    await fill(form, 'Approve', 'check');
    await submit(form);

    const alert = await within(form).findByText(
      'The check could not reach the API, so the result is still unknown.',
    );
    expect(alert).toBeInTheDocument();
    expect(within(form).queryByRole('button', { name: 'Retry' })).toBeNull();
    await userEvent.click(within(form).getByRole('button', { name: 'Check again' }));
    expect(
      await within(form).findByText('It was not recorded, so you can send it again.'),
    ).toBeInTheDocument();
    expect(harness.sent).toHaveLength(1);
  });

  it('shows the fixed unknown-outcome line during the re-read', async () => {
    let reads = 0;
    serve([drop]);
    server.use(
      http.get(`*/api/v1/risk/briefs/${briefId(0)}/decisions`, () => {
        reads += 1;
        return reads === 1 ? HttpResponse.json({ items: [] }) : hang();
      }),
    );
    const form = await openForm();

    await fill(form, 'Approve', 'wait');
    await submit(form);

    expect(await within(form).findByText(COPY.unknownOutcome)).toBeInTheDocument();
  });
});

describe('the chain in its other states', () => {
  it('loading: skeletons, and the form cannot be sent without the head', async () => {
    server.use(http.get(`*/api/v1/risk/briefs/${briefId(0)}/decisions`, hang));
    renderRoute(`/classic/briefs/${briefId(0)}`);
    const form = await screen.findByRole('form', { name: 'Record a decision' });

    expect(within(chainRegion()).getByText('Loading the decision chain…')).toBeInTheDocument();
    await userEvent.click(within(form).getByRole('radio', { name: 'Approve' }));
    await userEvent.type(within(form).getByLabelText('Your name'), 'Owner');
    expect(within(form).getByRole('button', { name: 'Record decision' })).toBeDisabled();
  });

  it('error: the message and Retry', async () => {
    let fail = true;
    server.use(
      http.get(`*/api/v1/risk/briefs/${briefId(0)}/decisions`, () =>
        fail ? refuse(422, 'INVALID_REQUEST', [], 'rid-chain-bad') : undefined,
      ),
    );
    renderRoute(`/classic/briefs/${briefId(0)}`);

    const alert = await within(
      await screen.findByRole('region', { name: 'Decision chain' }),
    ).findByRole('alert');
    expect(alert).toHaveTextContent('rid-chain-bad');
    fail = false;
    await userEvent.click(within(alert).getByRole('button', { name: 'Retry' }));
    expect(await within(chainRegion()).findByText(COPY.emptyDecisionChain)).toBeInTheDocument();
  });

  it('marks entries past twenty in parentheses, and shows an entry without a note', async () => {
    const many = Array.from({ length: 21 }, (_, index) => ({
      ...firstDecision,
      id: `${String(index).padStart(8, '0')}-0000-4000-8000-000000000000`,
      note: index === 20 ? null : `n${index}`,
      supersedes_id:
        index === 0 ? null : `${String(index - 1).padStart(8, '0')}-0000-4000-8000-000000000000`,
    }));
    server.use(chainHandler(() => many));
    renderRoute(`/classic/briefs/${briefId(0)}`);

    expect(
      await within(await screen.findByRole('region', { name: 'Decision chain' })).findByText(
        '(21)',
      ),
    ).toBeInTheDocument();
    expect(within(chainRegion()).getByText('No note.')).toBeInTheDocument();
    expect(within(chainRegion()).getByRole('link', { name: 'supersedes ⑳' })).toBeInTheDocument();
  });
});
