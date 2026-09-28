/**
 * The CEO inbox in its four states (spec §7.2, §8.7, AC-F-4, AC-F-14), from the recorded fixtures.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { COPY } from '@/copy';
import { AUTO_UNRESOLVED } from '@/panels/CeoInbox';
import { useSession } from '@/state/session';

import { briefId, hang, listBody, refuse } from '../support/api';
import { autoRun } from '../support/fixtures';
import { renderRoute } from '../support/render';
import { server } from '../support/server';

async function rows() {
  const list = await screen.findByRole('list', { name: 'Briefs, executive-worthy first' });
  return within(list).getAllByRole('listitem');
}

describe('the inbox: success', () => {
  it('pins CUST-007 CRITICAL · EXECUTIVE, then CUST-025 and CUST-036, all PENDING', async () => {
    renderRoute('/classic/inbox');

    const items = await rows();
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringMatching(/^CRITICAL·EXECUTIVEMeridian Textiles CUST-007PENDING$/),
      expect.stringMatching(/^WATCH.* CUST-025PENDING$/),
      expect.stringMatching(/^WATCH.* CUST-036PENDING$/),
    ]);
    expect(screen.getByText('3 briefs, 3 awaiting your decision.')).toBeInTheDocument();
  });

  it('states the snapshot: as_of, fingerprint, versions and customers per band', async () => {
    renderRoute('/classic/inbox');
    await rows();

    expect(screen.getByText('2026-09-18')).toBeInTheDocument();
    expect(screen.getByText('1d891b0b543f · rules 1 · linker 1')).toBeInTheDocument();
    expect(screen.getByText('1 CRITICAL · 2 WATCH · 47 NONE')).toBeInTheDocument();
    expect(screen.getByText(COPY.bandLegend)).toBeInTheDocument();
    expect(screen.queryByLabelText('Snapshot at this date')).not.toBeInTheDocument();
  });

  it('shows the API calls behind it: the list, the customers and one per brief', async () => {
    renderRoute('/classic/inbox');
    await rows();

    await userEvent.click(screen.getByText('Show the API call'));
    const table = screen.getByRole('table', { name: 'Requests behind this panel' });
    const routes = within(table)
      .getAllByRole('row')
      .slice(1)
      .map((row) => (row as HTMLTableRowElement).cells[0]?.textContent);
    expect(routes).toEqual([
      'GET /api/v1/risk/assessments?as_of=2026-09-18&limit=500&offset=0',
      'GET /api/v1/entities/customers?limit=500&offset=0',
      `GET /api/v1/risk/briefs/${briefId(0)}`,
      `GET /api/v1/risk/briefs/${briefId(1)}`,
      `GET /api/v1/risk/briefs/${briefId(2)}`,
    ]);
    expect(within(table).getAllByText(/^fixture\d+$/)).toHaveLength(5);
  });

  it('opens a brief from its row, keeping the query, and selects it', async () => {
    const { router } = renderRoute('/classic/inbox?as_of=2026-09-18');
    const [, second] = await rows();

    await userEvent.click(within(second as HTMLElement).getByRole('link'));
    expect(router.state.location.pathname).toBe(`/classic/briefs/${briefId(1)}`);
    expect(router.state.location.search).toBe('?as_of=2026-09-18');
    expect(useSession.getState().selectedBriefId).toBe(briefId(1));
    await screen.findByRole('heading', { level: 1, name: /CUST-025/ });
  });

  it('lets the user choose between two snapshots at one date, by fingerprint', async () => {
    const body = listBody();
    const other = 'c'.repeat(64);
    const copies = body.items.slice(0, 1).map((item) => ({
      ...item,
      id: `d${item.id.slice(1)}`,
      layer1_fingerprint: other,
    }));
    server.use(
      http.get('*/api/v1/risk/assessments', () =>
        HttpResponse.json({ ...body, items: [...body.items, ...copies], total: 51 }),
      ),
    );
    const { router } = renderRoute('/classic/inbox');
    await rows();

    const select = screen.getByLabelText('Snapshot at this date');
    expect(
      within(select)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['1d891b0b543f · rules 1 · linker 1', 'cccccccccccc · rules 1 · linker 1']);
    await userEvent.selectOptions(select, within(select).getAllByRole('option')[1] as HTMLElement);
    expect(router.state.location.search).toContain('snapshot=cccccccccccc');
    await waitFor(async () => expect(await rows()).toHaveLength(1));
  });

  it('shows policy and template versions when an assessment has two briefs', async () => {
    const body = listBody();
    const [top, second] = body.items.filter((item) => item.brief_ids.length > 0);
    const doubled = body.items.map((item) =>
      item.id === top?.id
        ? { ...item, brief_ids: [...item.brief_ids, ...(second?.brief_ids ?? [])] }
        : item,
    );
    server.use(
      http.get('*/api/v1/risk/assessments', () => HttpResponse.json({ ...body, items: doubled })),
    );
    renderRoute('/classic/inbox');

    const items = await rows();
    expect(items).toHaveLength(4);
    expect(within(items[0] as HTMLElement).getByText('policy 1 · template 1')).toBeInTheDocument();
  });
});

describe('the inbox: loading, empty and error', () => {
  it('loading: skeletons while the list is in flight', () => {
    server.use(http.get('*/api/v1/risk/assessments', hang));
    renderRoute('/classic/inbox');

    expect(screen.getByText('Loading the CEO inbox…')).toBeInTheDocument();
  });

  it('empty, no assessment at the date: the fixed copy and a Run assessment button', async () => {
    server.use(
      http.get('*/api/v1/risk/assessments', () =>
        HttpResponse.json({ items: [], total: 0, limit: 500, offset: 0 }),
      ),
    );
    renderRoute('/classic/inbox');

    expect(await screen.findByText(COPY.inboxNoAssessment)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Run assessment' })).toHaveLength(2);
  });

  it('empty, assessments but no brief: the fixed copy', async () => {
    const body = listBody();
    server.use(
      http.get('*/api/v1/risk/assessments', () =>
        HttpResponse.json({
          ...body,
          items: body.items.map((item) => ({ ...item, brief_ids: [] })),
        }),
      ),
    );
    renderRoute('/classic/inbox');

    expect(await screen.findByText(COPY.inboxNoBrief)).toBeInTheDocument();
  });

  it('under Auto before any Auto run: how to get a date', async () => {
    renderRoute('/classic/inbox?as_of=auto');

    expect(await screen.findByText(AUTO_UNRESOLVED)).toBeInTheDocument();
  });

  it('under Auto after an Auto run: the snapshot at the date it resolved to', async () => {
    const [run, detail] = autoRun();
    const ids = (run?.body as { items: { assessment_id: string }[] }).items.map(
      (item) => item.assessment_id,
    );
    useSession.setState({
      lastRun: {
        requested: { kind: 'auto' },
        asOf: (detail?.body as { as_of: string }).as_of,
        status: 201,
        assessmentIds: ids,
        briefCount: 4,
        createdCount: 50,
      },
    });
    renderRoute('/classic/inbox?as_of=auto');

    expect(await rows()).toHaveLength(4);
    expect(screen.getByText('2026-08-27')).toBeInTheDocument();
  });

  it('error: the message, code and request id, and Retry recovers', async () => {
    let fail = true;
    server.use(
      http.get('*/api/v1/risk/assessments', () =>
        fail ? refuse(422, 'INVALID_REQUEST', [], 'rid-bad') : HttpResponse.json(listBody()),
      ),
    );
    renderRoute('/classic/inbox');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('INVALID_REQUEST');
    expect(alert).toHaveTextContent('rid-bad');
    fail = false;
    await userEvent.click(within(alert).getByRole('button', { name: 'Retry' }));
    expect(await rows()).toHaveLength(3);
  });

  it('error in one brief: the inbox is not rendered partially', async () => {
    server.use(
      http.get(`*/api/v1/risk/briefs/${briefId(2)}`, () => refuse(404, 'BRIEF_NOT_FOUND')),
    );
    renderRoute('/classic/inbox');

    expect(await screen.findByRole('alert')).toHaveTextContent('BRIEF_NOT_FOUND');
    expect(screen.queryByRole('list', { name: 'Briefs, executive-worthy first' })).toBeNull();
  });
});
