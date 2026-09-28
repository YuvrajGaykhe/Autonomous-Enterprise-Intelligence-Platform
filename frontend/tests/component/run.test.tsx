/**
 * Run assessment (spec §6.6, §7.6, §8.2, D-F-14, R-F-7): 201 and 200, Auto, the refusals, and an
 * unknown outcome, which is re-read before any retry is offered.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { COPY } from '@/copy';
import { OUTCOME_MESSAGES } from '@/domain/outcomes';
import { useSession } from '@/state/session';

import { answer, drop, hang, refuse } from '../support/api';
import { autoRun, loadExchanges, type RecordedExchange } from '../support/fixtures';
import { renderRoute } from '../support/render';
import { server } from '../support/server';

const [firstRun, repeatRun] = loadExchanges('assessment-runs.json') as [
  RecordedExchange,
  RecordedExchange,
];
const [autoPost, , , ...autoRest] = autoRun();
const unresolved = autoRest.at(-1) as RecordedExchange;

interface Sent {
  path: string;
  body: unknown;
}

/** Serve POST /risk/assessments with `respond`, and count requests with `limit=1`. */
function serveRun(respond: () => Response | Promise<Response>, totals: number[] = [50, 50]) {
  const sent: Sent[] = [];
  const counts: string[] = [];
  server.use(
    http.post('*/api/v1/risk/assessments', async ({ request }) => {
      sent.push({ path: new URL(request.url).pathname, body: await request.json() });
      return respond();
    }),
    http.get('*/api/v1/risk/assessments', ({ request, requestId }) => {
      const url = new URL(request.url);
      if (url.searchParams.get('limit') !== '1') return undefined;
      counts.push(url.search);
      const total = totals[Math.min(counts.length - 1, totals.length - 1)] ?? 0;
      return HttpResponse.json(
        { items: [], total, limit: 1, offset: 0 },
        { headers: { 'X-Request-ID': requestId } },
      );
    }),
  );
  return { sent, counts };
}

function runButton() {
  return within(screen.getByRole('banner')).getByRole('button', {
    name: /Run assessment|Assessing/,
  });
}

async function status() {
  return await screen.findByRole('status', { name: 'Assessment run' });
}

describe('a run that answers', () => {
  it('201 at the chosen date: sends the date and csv_demo only, then shows the inbox', async () => {
    const { sent, counts } = serveRun(() => answer(firstRun, 'rid-run'));
    const { router } = renderRoute('/classic?as_of=2026-09-18&snapshot=ffffffffffff');

    await userEvent.click(runButton());

    expect(await status()).toHaveTextContent(
      'Assessed 50 customers at 2026-09-18: 3 briefs, 50 new results.',
    );
    expect(sent).toEqual([
      {
        path: '/api/v1/risk/assessments',
        body: { as_of: '2026-09-18', source_system: 'csv_demo' },
      },
    ]);
    expect(counts).toEqual(['?as_of=2026-09-18&limit=1&offset=0']);
    expect(router.state.location.pathname).toBe('/classic/inbox');
    expect(router.state.location.search).toBe('?as_of=2026-09-18');
    expect(useSession.getState().lastRun).toMatchObject({
      asOf: '2026-09-18',
      status: 201,
      briefCount: 3,
      createdCount: 50,
    });
    expect(await screen.findAllByTestId('inbox-row')).toHaveLength(3);
  });

  it('200: every result existed, so nothing was written', async () => {
    serveRun(() => answer(repeatRun, 'rid-run'));
    renderRoute('/classic');

    await userEvent.click(runButton());

    expect(await status()).toHaveTextContent(
      'Already assessed at 2026-09-18: all 50 results existed, so nothing was written.',
    );
  });

  it('Auto sends as_of null and shows the snapshot at the date it resolved to', async () => {
    const { sent, counts } = serveRun(() => answer(autoPost as RecordedExchange, 'rid-auto'));
    renderRoute('/classic?as_of=auto');

    await userEvent.click(runButton());

    expect(await status()).toHaveTextContent(
      'Assessed 50 customers at 2026-08-27: 4 briefs, 50 new results.',
    );
    expect(sent[0]?.body).toEqual({ as_of: null, source_system: 'csv_demo' });
    expect(counts).toEqual(['?limit=1&offset=0']);
    expect(await screen.findAllByTestId('inbox-row')).toHaveLength(4);
  });

  it('Auto whose date cannot be read back still reports the run', async () => {
    serveRun(() => answer(autoPost as RecordedExchange, 'rid-auto'));
    server.use(
      http.get('*/api/v1/risk/assessments/:id', () => refuse(404, 'ASSESSMENT_NOT_FOUND')),
    );
    renderRoute('/classic?as_of=auto');

    await userEvent.click(runButton());

    expect(await status()).toHaveTextContent('Assessed 50 customers at the resolved date');
    expect(useSession.getState().lastRun?.asOf).toBeNull();
  });

  it('disables the button while the run is in flight', async () => {
    serveRun(hang);
    renderRoute('/classic');

    await userEvent.click(runButton());

    await waitFor(() => expect(runButton()).toBeDisabled());
    expect(runButton()).toHaveTextContent('Assessing…');
    expect(await status()).toHaveTextContent('Assessing every customer at 2026-09-18…');
    expect(within(await status()).queryByRole('button', { name: 'Dismiss' })).toBeNull();
  });

  it('can be dismissed', async () => {
    serveRun(() => answer(repeatRun, 'rid-run'));
    renderRoute('/classic');
    await userEvent.click(runButton());
    await status();

    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByRole('status', { name: 'Assessment run' })).toBeNull();
  });
});

describe('a run that is refused (§7.6)', () => {
  it('422 SCOPE_UNRESOLVED, as recorded: choose an explicit date, and stay', async () => {
    serveRun(() => answer(unresolved, 'rid-scope'));
    const { router } = renderRoute('/classic?as_of=auto');

    await userEvent.click(runButton());

    expect(await screen.findByRole('alert', { name: 'Assessment run' })).toHaveTextContent(
      OUTCOME_MESSAGES.scopeUnresolved,
    );
    expect(router.state.location.pathname).toBe('/classic');
  });

  it('422 INVALID_REQUEST: the field messages', async () => {
    serveRun(() =>
      refuse(422, 'INVALID_REQUEST', [{ loc: ['body', 'as_of'], message: 'bad date', type: 't' }]),
    );
    renderRoute('/classic');

    await userEvent.click(runButton());

    const alert = await screen.findByRole('alert', { name: 'Assessment run' });
    expect(alert).toHaveTextContent(OUTCOME_MESSAGES.invalid);
    expect(alert).toHaveTextContent('body.as_of: bad date');
  });

  it('500: nothing was written, with the request id, and Retry sends again', async () => {
    let calls = 0;
    const { sent } = serveRun(() => {
      calls += 1;
      return calls === 1 ? refuse(500, 'INTERNAL_ERROR', null, 'rid-500') : answer(repeatRun, 'r');
    });
    renderRoute('/classic');

    await userEvent.click(runButton());
    const alert = await screen.findByRole('alert', { name: 'Assessment run' });
    expect(alert).toHaveTextContent(OUTCOME_MESSAGES.nothingWritten);
    expect(alert).toHaveTextContent('request rid-500');

    await userEvent.click(within(alert).getByRole('button', { name: 'Retry' }));
    expect(await status()).toHaveTextContent('Already assessed');
    expect(sent).toHaveLength(2);
  });

  it('a 2xx body the frontend cannot read: the error state, and no retry', async () => {
    serveRun(() => HttpResponse.json({ items: 'nope' }, { status: 201 }));
    renderRoute('/classic');

    await userEvent.click(runButton());

    const alert = await screen.findByRole('alert', { name: 'Assessment run' });
    expect(alert).toHaveTextContent('CONTRACT_ERROR');
    expect(within(alert).queryByRole('button', { name: 'Retry' })).toBeNull();
  });

  it('the count before the POST fails: nothing is sent', async () => {
    const { sent } = serveRun(() => answer(repeatRun, 'r'));
    server.use(http.get('*/api/v1/risk/assessments', () => refuse(404, 'NOT_FOUND')));
    renderRoute('/classic');

    await userEvent.click(runButton());

    const alert = await screen.findByRole('alert', { name: 'Assessment run' });
    expect(alert).toHaveTextContent('The assessment was not sent');
    expect(sent).toEqual([]);
    await userEvent.click(within(alert).getByRole('button', { name: 'Retry' }));
    expect(sent).toEqual([]);
  });
});

describe('a run whose outcome is unknown (R-F-7)', () => {
  it('re-reads, and reports a recorded run without offering a retry', async () => {
    const { sent, counts } = serveRun(drop, [50, 100]);
    renderRoute('/classic');

    await userEvent.click(runButton());

    expect(await status()).toHaveTextContent('The assessment was recorded.');
    expect(counts).toHaveLength(2);
    expect(sent).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
    await userEvent.click(screen.getByRole('link', { name: 'Show the inbox' }));
    expect(await screen.findAllByTestId('inbox-row')).toHaveLength(3);
  });

  it('re-reads, and offers a retry only when nothing new was recorded', async () => {
    let calls = 0;
    const { sent } = serveRun(() => {
      calls += 1;
      return calls === 1 ? HttpResponse.error() : answer(repeatRun, 'r');
    }, [50, 50]);
    renderRoute('/classic');

    await userEvent.click(runButton());

    expect(await status()).toHaveTextContent(
      'Nothing new was recorded, so running it again is safe.',
    );
    expect(sent).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await status()).toHaveTextContent('Already assessed');
    expect(sent).toHaveLength(2);
  });

  it('shows the unknown-outcome message while it re-reads', async () => {
    let counted = 0;
    serveRun(drop);
    server.use(
      http.get('*/api/v1/risk/assessments', () => {
        counted += 1;
        return counted === 1
          ? HttpResponse.json({ items: [], total: 50, limit: 1, offset: 0 })
          : hang();
      }),
    );
    renderRoute('/classic');

    await userEvent.click(runButton());

    expect(await screen.findByText(COPY.unknownOutcome)).toBeInTheDocument();
    expect(runButton()).toBeDisabled();
  });

  it('when the re-read fails too, offers Check again and never a retry', async () => {
    let counted = 0;
    const { sent } = serveRun(drop);
    server.use(
      http.get('*/api/v1/risk/assessments', () => {
        counted += 1;
        if (counted === 1) return HttpResponse.json({ items: [], total: 50, limit: 1, offset: 0 });
        if (counted === 2) return refuse(404, 'NOT_FOUND', null, 'rid-check');
        return HttpResponse.json({ items: [], total: 100, limit: 1, offset: 0 });
      }),
    );
    renderRoute('/classic');

    await userEvent.click(runButton());
    const alert = await screen.findByRole('alert', { name: 'Assessment run' });
    expect(alert).toHaveTextContent('The check could not reach the API');
    expect(within(alert).queryByRole('button', { name: 'Retry' })).toBeNull();

    await userEvent.click(within(alert).getByRole('button', { name: 'Check again' }));
    expect(await status()).toHaveTextContent('The assessment was recorded.');
    expect(sent).toHaveLength(1);
  });
});
