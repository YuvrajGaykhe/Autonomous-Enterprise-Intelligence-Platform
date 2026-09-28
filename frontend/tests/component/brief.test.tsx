/**
 * Brief detail (spec §7.3, §7.4, §8.4): every section in order, the evidence links, and the four
 * states, from the recorded briefs.
 */

import { readFileSync } from 'node:fs';

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { COPY, fill } from '@/copy';
import { useSession } from '@/state/session';

import {
  answer,
  briefBodies,
  briefId,
  flowExchange,
  hang,
  recordedRefusal,
  refuse,
} from '../support/api';
import { REPO_ROOT } from '../support/fixtures';
import { renderRoute } from '../support/render';
import { server } from '../support/server';

const golden = readFileSync(`${REPO_ROOT}tests/golden/vs01_cust007_brief.txt`, 'utf8');

const SECTIONS = [
  'Identity',
  'Risk state and why',
  'Signals and derivations',
  'Evidence: tickets',
  'Evidence: documents',
  'Evidence: deals',
  'Evidence: cited quotes',
  'Commercial context (per currency)',
  'Conflict and how it was resolved',
  'Recorded dissent',
  'Policy and contract context',
  'Chronic backlog',
  'Recommended actions',
  'Escalation path',
  'Narrative',
  'Technical',
  'Your decision',
  'Decision chain',
];

async function openBrief(index = 0) {
  const view = renderRoute(`/classic/briefs/${briefId(index)}?as_of=2026-09-18`);
  await screen.findByRole('region', { name: 'Technical' });
  return view;
}

describe('the brief: success', () => {
  it('shows every section of §7.3 in order, then the decision and the chain', async () => {
    await openBrief();

    const headings = screen
      .getAllByRole('heading', { level: 2 })
      .filter((heading) => heading.closest('nav') === null)
      .map((heading) => heading.textContent);
    expect(headings).toEqual(SECTIONS);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Meridian Textiles CUST-007',
    );
  });

  it('shows the narrative verbatim, byte for byte the golden brief', async () => {
    await openBrief();

    const narrative = screen.getByRole('region', { name: 'Narrative' });
    expect(narrative.querySelector('pre')?.textContent).toBe(golden);
  });

  it('shows decision_status as the state, and the stored status only under Technical', async () => {
    await openBrief();

    const header = screen.getByRole('heading', { level: 1 }).parentElement as HTMLElement;
    expect(within(header).getByText('PENDING')).toBeInTheDocument();
    expect(within(header).queryByText('DRAFT')).toBeNull();
    const technical = screen.getByRole('region', { name: 'Technical' });
    expect(within(technical).getByText('DRAFT')).toBeInTheDocument();
    expect(within(technical).getByText(briefId(0))).toBeInTheDocument();
  });

  it('quotes each cited span from the document text, as the golden brief does', async () => {
    await openBrief();

    const quotes = screen.getByRole('region', { name: 'Evidence: cited quotes' });
    const blocks = await within(quotes).findAllByRole('blockquote');
    for (const block of blocks) {
      const text = (block.textContent ?? '').replace(/^“|”$/g, '');
      expect(golden).toContain(`: "${text}"`);
    }
    expect(blocks).toHaveLength(3);
  });

  it('opens a ticket record with its cited field marked', async () => {
    await openBrief();

    const tickets = screen.getByRole('region', { name: 'Evidence: tickets' });
    await userEvent.click(
      within(tickets).getAllByRole('button', { name: /created_at$/ })[0] as HTMLElement,
    );
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading')).toHaveTextContent(/^support_tickets TKT-\d{3}$/);
    expect(await within(dialog).findByText('created_at (cited)')).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('opens a document span with the span marked', async () => {
    await openBrief();

    const quotes = screen.getByRole('region', { name: 'Evidence: cited quotes' });
    const [link] = within(quotes).getAllByRole('button', { name: /^DOC-\d{3} \[\d+, \d+\)$/ });
    await userEvent.click(link as HTMLElement);
    const dialog = await screen.findByRole('dialog');
    const mark = await within(dialog).findByText((_text, element) => element?.tagName === 'MARK');
    expect(golden).toContain(`: "${mark.textContent}"`);
  });

  it('says so when a cited record or span is not in Layer 1', async () => {
    server.use(
      http.get('*/api/v1/entities/:type', () =>
        HttpResponse.json({ items: [], total: 0, limit: 500, offset: 0 }),
      ),
    );
    await openBrief();

    const deals = screen.getByRole('region', { name: 'Evidence: deals' });
    await userEvent.click(
      within(deals).getAllByRole('button', { name: /^deals DEAL-\d{3} stage$/ })[0] as HTMLElement,
    );
    expect(
      await screen.findByText(/^No deals record DEAL-\d{3} exists in Layer 1/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Close' }));

    const quotes = screen.getByRole('region', { name: 'Evidence: cited quotes' });
    expect(
      await within(quotes).findAllByText('The cited text cannot be read from Layer 1.'),
    ).toHaveLength(3);
    await userEvent.click(within(quotes).getAllByRole('button')[0] as HTMLElement);
    expect(await screen.findByText(/^No document DOC-\d{3} exists in Layer 1/)).toBeInTheDocument();
  });

  it('refuses a span that lies outside the document', async () => {
    const [brief] = briefBodies();
    const payload = brief?.payload as {
      cited_spans: { citation: { start: number; end: number } }[];
    };
    const wide = {
      ...brief,
      payload: {
        ...payload,
        cited_spans: payload.cited_spans.map((span) => ({
          ...span,
          citation: { ...span.citation, start: 0, end: 99_999 },
        })),
      },
    };
    server.use(http.get(`*/api/v1/risk/briefs/${briefId(0)}`, () => HttpResponse.json(wide)));
    await openBrief();

    const quotes = screen.getByRole('region', { name: 'Evidence: cited quotes' });
    await userEvent.click(within(quotes).getAllByRole('button')[0] as HTMLElement);
    expect(await screen.findByText(/lies outside document DOC-\d{3}'s text/)).toBeInTheDocument();
  });

  it('shows the empty sections of a brief with no conflict, dissent, deal or document', async () => {
    await openBrief(2);

    expect(screen.getByText('No two functions conflict on this customer.')).toBeInTheDocument();
    expect(screen.getByText('No position was overruled.')).toBeInTheDocument();
    expect(screen.getByText('No document links to this customer.')).toBeInTheDocument();
    expect(screen.getByText('No span is cited.')).toBeInTheDocument();
    expect(
      screen.getByText('No action is recommended, because no function stated a position.'),
    ).toBeInTheDocument();
  });

  it('opening a brief makes it the selected one (§9.2)', async () => {
    await openBrief(1);

    expect(useSession.getState().selectedBriefId).toBe(briefId(1));
  });

  it('shows the requests behind the page', async () => {
    await openBrief();

    await userEvent.click(screen.getByText('Show the API call'));
    const table = screen.getByRole('table', { name: 'Requests behind this panel' });
    expect(within(table).getByText(`GET /api/v1/risk/briefs/${briefId(0)}`)).toBeInTheDocument();
    expect(
      within(table).getByText(`GET /api/v1/risk/briefs/${briefId(0)}/decisions`),
    ).toBeInTheDocument();
  });
});

describe('the brief: loading, not found, unsupported and error', () => {
  it('loading: skeletons', () => {
    server.use(http.get('*/api/v1/risk/briefs/:id', hang));
    renderRoute(`/classic/briefs/${briefId(0)}`);

    expect(screen.getByText('Loading the brief…')).toBeInTheDocument();
  });

  it('not found, as recorded: the not-found state and a way back to the inbox', async () => {
    const notFound = recordedRefusal('BRIEF_NOT_FOUND');
    const missing = notFound.path.split('/').pop() ?? '';
    const chain = flowExchange((item) => item.path.endsWith(`${missing}/decisions`));
    server.use(
      http.get(`*${notFound.path}`, () => answer(notFound, 'rid-404')),
      http.get(`*${chain.path}`, () => answer(chain, 'rid-404b')),
    );
    renderRoute(`/classic/briefs/${missing}?as_of=2026-09-18`);

    expect(await screen.findByText('No brief exists at this address.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Return to the inbox' })).toHaveAttribute(
      'href',
      '/classic/inbox?as_of=2026-09-18',
    );
  });

  it('a payload version it does not support: that message and no section', async () => {
    const [brief] = briefBodies();
    server.use(
      http.get(`*/api/v1/risk/briefs/${briefId(0)}`, () =>
        HttpResponse.json({ ...brief, payload: { ...brief?.payload, payload_version: 2 } }),
      ),
    );
    renderRoute(`/classic/briefs/${briefId(0)}`);

    expect(await screen.findByText(fill(COPY.unsupportedBrief, { n: 2 }))).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Identity' })).toBeNull();
    expect(screen.queryByRole('form', { name: 'Record a decision' })).toBeNull();
  });

  it('error: the message, the code and the request id, and Retry', async () => {
    let fail = true;
    const [brief] = briefBodies();
    server.use(
      http.get(`*/api/v1/risk/briefs/${briefId(0)}`, () =>
        fail
          ? refuse(422, 'INVALID_REQUEST', [], 'rid-brief')
          : answer({ method: 'GET', path: '', status: 200, body: brief }, 'rid-ok'),
      ),
    );
    renderRoute(`/classic/briefs/${briefId(0)}`);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('rid-brief');
    fail = false;
    await userEvent.click(within(alert).getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('region', { name: 'Technical' })).toBeInTheDocument();
  });
});
