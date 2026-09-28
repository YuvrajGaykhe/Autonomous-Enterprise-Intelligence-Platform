/**
 * The agent panels (spec §8.3, §9.2), the Classic overview's About panel and the staff directory
 * (§10), each in its four states, from the recorded fixtures.
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { COPY, ROLE_LINES } from '@/copy';
import { AUTO_UNRESOLVED } from '@/panels/CeoInbox';
import { useSession } from '@/state/session';

import { briefBodies, briefId, hang, listBody, refuse } from '../support/api';
import { recordedBody } from '../support/fixtures';
import { renderRoute } from '../support/render';
import { server } from '../support/server';

async function openAgent(id: string, query = '') {
  const view = renderRoute(`/classic/agents/${id}${query}`);
  await screen.findByRole('heading', { level: 1 });
  return view;
}

function region(name: string) {
  return screen.getByRole('region', { name });
}

describe('the overview and the staff directory (§9.2, §10)', () => {
  it('states that the agents are rule-based, and lists every agent with its role', async () => {
    renderRoute('/classic');

    const about = screen.getByRole('region', { name: 'About the agents' });
    expect(within(about).getByText(COPY.aboutAgents)).toBeInTheDocument();
    await within(about).findByText('CSV_DEMO_AGENT');
    expect(within(about).getAllByRole('link')).toHaveLength(11);
    expect(within(about).getAllByText(ROLE_LINES.connector)).toHaveLength(3);
  });

  it('mirrors every agent in the Classic navigation, keeping the query', async () => {
    renderRoute('/classic?as_of=2026-09-18');

    const directory = screen.getByRole('list', { name: 'Staff directory' });
    await within(directory).findByText('REST_MOCK_AGENT');
    expect(within(directory).getByRole('link', { name: 'LINKER_AGENT' })).toHaveAttribute(
      'href',
      '/classic/agents/linker?as_of=2026-09-18',
    );
  });

  it('says when the connectors are loading or cannot be listed', async () => {
    server.use(http.get('*/api/v1/sources', hang));
    const { unmount } = renderRoute('/classic');
    expect(screen.getByText('Loading the connectors…')).toBeInTheDocument();
    unmount();

    server.use(http.get('*/api/v1/sources', () => refuse(404, 'NOT_FOUND')));
    renderRoute('/classic');
    expect(await screen.findByText('The connectors could not be listed.')).toBeInTheDocument();
  });
});

describe('a connector (CSV_DEMO_AGENT)', () => {
  it('shows its capabilities, its health check and its latest runs, with Show the API call', async () => {
    await openAgent('csv_demo');

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('CSV_DEMO_AGENT');
    expect(screen.getByText('app/connectors/*')).toBeInTheDocument();
    expect(screen.getByText(ROLE_LINES.connector)).toBeInTheDocument();
    expect(await within(region('Capabilities')).findByText('csv')).toBeInTheDocument();
    expect(await within(region('Health check')).findByText('healthy')).toBeInTheDocument();
    expect(within(region('Health check')).getByText('not measured')).toBeInTheDocument();
    const runs = region('Latest ingestion runs');
    expect(await within(runs).findByText('SUCCESS')).toBeInTheDocument();
    expect(within(runs).getByText(/fetched 233 · inserted 233/)).toBeInTheDocument();

    await userEvent.click(within(runs).getByRole('button', { name: 'Show errors' }));
    expect(await within(runs).findByText('This run recorded no error.')).toBeInTheDocument();
    await userEvent.click(within(runs).getByRole('button', { name: 'Hide errors' }));
    expect(within(runs).queryByText('This run recorded no error.')).toBeNull();
  });

  it('lists a run error, and a mock source with a latency and no run', async () => {
    type Page = { items: unknown[]; total: number; limit: number; offset: number };
    const recordedRuns = recordedBody<{ items: { run_id: string }[] }>(
      'ingestion.json',
      'GET',
      '/api/v1/ingestion/runs?limit=500&offset=0',
    );
    const runId = recordedRuns.items[0]?.run_id ?? '';
    const errorList = recordedBody<Page>(
      'ingestion.json',
      'GET',
      `/api/v1/ingestion/runs/${runId}/errors?limit=500&offset=0`,
    );
    server.use(
      http.get('*/api/v1/ingestion/runs/:id/errors', () =>
        HttpResponse.json({
          ...errorList,
          total: 1,
          items: [
            {
              id: '00000000-0000-4000-8000-00000000000e',
              severity: 'ERROR',
              code: 'MISSING_FIELD',
              message: 'a required field is empty',
              source_system: 'csv_demo',
              source_entity: 'customers',
              source_id: 'row-9',
              created_at: '2026-09-28T00:00:00Z',
              findings: [],
            },
          ],
        }),
      ),
    );
    const { unmount } = await openAgent('csv_demo');
    const runs = region('Latest ingestion runs');
    await userEvent.click(await within(runs).findByRole('button', { name: 'Show errors' }));
    expect(await within(runs).findByText(/a required field is empty/)).toBeInTheDocument();
    expect(within(runs).getByText('(customers row-9)')).toBeInTheDocument();
    unmount();

    await openAgent('odoo_mock');
    expect(await within(region('Health check')).findByText('unhealthy')).toBeInTheDocument();
    expect(within(region('Health check')).getByText(/^\d+ ms$/)).toBeInTheDocument();
    expect(
      await within(region('Latest ingestion runs')).findByText(
        'No ingestion run from this source yet.',
      ),
    ).toBeInTheDocument();
  });

  it('loading and error states', async () => {
    server.use(http.get('*/api/v1/sources/:source/health', hang));
    const { unmount } = await openAgent('csv_demo');
    expect(
      within(region('Health check')).getByText('Loading the health check…'),
    ).toBeInTheDocument();
    unmount();

    server.use(
      http.get('*/api/v1/ingestion/runs', () => refuse(422, 'INVALID_REQUEST', [], 'rid-runs')),
    );
    await openAgent('csv_demo');
    expect(await within(region('Latest ingestion runs')).findByRole('alert')).toHaveTextContent(
      'rid-runs',
    );
  });

  it('an unknown agent is not found, once the sources have answered', async () => {
    renderRoute('/classic/agents/nobody');

    expect(screen.getByText('Loading the agent roster…')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });

  it('an unknown agent while the sources fail: the error state', async () => {
    server.use(http.get('*/api/v1/sources', () => refuse(404, 'NOT_FOUND', null, 'rid-src')));
    renderRoute('/classic/agents/nobody');

    expect(await screen.findByRole('alert')).toHaveTextContent('rid-src');
  });
});

describe('MEMORY', () => {
  it('shows the database, the seven totals, the metrics and the snapshot fingerprint', async () => {
    await openAgent('memory');

    expect(await within(region('Database')).findByText('ok')).toBeInTheDocument();
    const records = region('Canonical records');
    expect(await within(records).findByText('support_tickets')).toBeInTheDocument();
    expect(within(records).getByText('80')).toBeInTheDocument();
    expect(await within(region('Ingestion metrics')).findByText('233')).toBeInTheDocument();
    expect(
      await within(region('Snapshot')).findByText(
        '1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00',
      ),
    ).toBeInTheDocument();
  });

  it('empty: no records yet', async () => {
    server.use(
      http.get('*/api/v1/entities/:type', () =>
        HttpResponse.json({ items: [], total: 0, limit: 1, offset: 0 }),
      ),
    );
    await openAgent('memory');

    expect(await screen.findByText(COPY.memoryNoRecords)).toBeInTheDocument();
  });

  it('loading and error', async () => {
    server.use(http.get('*/api/v1/entities/:type', hang));
    const { unmount } = await openAgent('memory');
    expect(
      within(region('Canonical records')).getByText('Loading the record totals…'),
    ).toBeInTheDocument();
    unmount();

    server.use(
      http.get('*/api/v1/entities/:type', () => refuse(422, 'INVALID_REQUEST', [], 'rid-ent')),
    );
    await openAgent('memory');
    expect(await within(region('Canonical records')).findByRole('alert')).toHaveTextContent(
      'rid-ent',
    );
  });
});

describe('the agents of the selected customer (§9.2)', () => {
  it('LINKER shows the document links and cited spans of the inbox first row by default', async () => {
    await openAgent('linker');

    expect(await screen.findByText('Showing')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Meridian Textiles' })).toHaveAttribute(
      'href',
      `/classic/briefs/${briefId(0)}`,
    );
    const links = region('Document links');
    expect(within(links).getAllByText(/confidence, matching “/)).toHaveLength(6);
    expect(within(links).getAllByText(/matching “CUST-007”/)).toHaveLength(3);
    expect(await within(region('Cited spans')).findAllByRole('blockquote')).toHaveLength(3);
  });

  it('follows the selected brief, and says so when it has no link or span', async () => {
    useSession.setState({ selectedBriefId: briefId(1) });
    await openAgent('linker');

    expect(
      await screen.findByText(
        'The linker found no document naming this customer in this snapshot.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('No span is cited in this brief.')).toBeInTheDocument();
  });

  it('SIGNALS shows the band, the rules, the values and the derivations', async () => {
    await openAgent('signals');

    const band = await screen.findByRole('region', { name: 'Band and rules' });
    expect(within(band).getByText(/R-CRIT-001/)).toBeInTheDocument();
    expect(within(band).getByText(COPY.bandLegend)).toBeInTheDocument();
    expect(within(region('Signals')).getByText('S10 dominant_ticket_category')).toBeInTheDocument();
    expect(
      await within(region('Derivations')).findByText('open_ticket_count = 4'),
    ).toBeInTheDocument();
  });

  it('SALES and SUPPORT show their own positions only', async () => {
    const { unmount } = await openAgent('sales');
    const sales = await screen.findByRole('region', { name: 'SALES positions' });
    expect(sales.querySelector('ol')?.children).toHaveLength(1);
    expect(within(sales).getByText('ACCELERATE_DEAL_CLOSE')).toBeInTheDocument();
    unmount();

    await openAgent('support');
    const support = await screen.findByRole('region', { name: 'SUPPORT positions' });
    expect(support.querySelector('ol')?.children).toHaveLength(5);
  });

  it('SALES says so when the selected customer has no sales position', async () => {
    useSession.setState({ selectedBriefId: briefId(2) });
    await openAgent('sales');

    expect(
      await screen.findByText('SALES stated no position on this customer.'),
    ).toBeInTheDocument();
  });

  it('RECONCILER shows the conflict, the resolution, the dissent and the worthiness', async () => {
    await openAgent('reconciler');

    expect(
      await screen.findByRole('region', { name: 'Conflict and how it was resolved' }),
    ).toBeInTheDocument();
    expect(screen.getByText('CONF-001', { selector: 'span.font-semibold' })).toBeInTheDocument();
    expect(region('Recorded dissent')).toHaveTextContent('Overruled by CONF-001:');
    expect(within(region('Executive worthiness')).getByText('yes')).toBeInTheDocument();
  });

  it('BRIEF_WRITER shows the stored narrative verbatim with its hash and versions', async () => {
    await openAgent('brief-writer');

    const writer = await screen.findByRole('region', { name: 'Narrative' });
    expect(writer.querySelector('pre')?.textContent).toBe(String(briefBodies()[0]?.['narrative']));
    expect(
      within(region('The stored brief')).getByText(briefBodies()[0]?.payload_hash ?? ''),
    ).toBeInTheDocument();
  });

  it('CEO shows the inbox', async () => {
    await openAgent('ceo');

    expect(screen.getByText(ROLE_LINES.ceo)).toBeInTheDocument();
    expect(await screen.findAllByTestId('inbox-row')).toHaveLength(3);
  });

  it('a payload version it does not support: that message, in each brief panel', async () => {
    const [brief] = briefBodies();
    server.use(
      http.get(`*/api/v1/risk/briefs/${briefId(0)}`, () =>
        HttpResponse.json({ ...brief, payload: { ...brief?.payload, payload_version: 3 } }),
      ),
    );
    const { unmount } = await openAgent('linker');
    const message = 'This brief uses payload version 3, which this frontend does not support.';
    expect(await screen.findByText(message)).toBeInTheDocument();
    unmount();

    await openAgent('signals');
    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it('empty: no brief at the date, no assessment, and Auto before a run', async () => {
    const body = listBody();
    server.use(
      http.get('*/api/v1/risk/assessments', () =>
        HttpResponse.json({
          ...body,
          items: body.items.map((item) => ({ ...item, brief_ids: [] })),
        }),
      ),
    );
    let view = await openAgent('reconciler');
    expect(await screen.findByText(COPY.inboxNoBrief)).toBeInTheDocument();
    view.unmount();

    server.use(
      http.get('*/api/v1/risk/assessments', () =>
        HttpResponse.json({ items: [], total: 0, limit: 500, offset: 0 }),
      ),
    );
    view = await openAgent('sales');
    expect(await screen.findByText(COPY.inboxNoAssessment)).toBeInTheDocument();
    view.unmount();

    await openAgent('memory', '?as_of=auto');
    expect(await screen.findByText(AUTO_UNRESOLVED)).toBeInTheDocument();
  });

  it('loading and error', async () => {
    server.use(http.get('*/api/v1/risk/assessments/:id', hang));
    const { unmount } = await openAgent('signals');
    expect(await screen.findByText('Loading the assessment…')).toBeInTheDocument();
    unmount();

    server.use(
      http.get('*/api/v1/risk/assessments', () => refuse(422, 'INVALID_REQUEST', [], 'rid-list')),
    );
    await openAgent('support');
    expect(await screen.findByRole('alert')).toHaveTextContent('rid-list');
  });

  it('404 on the selected assessment: the not-found state and a way back to the inbox', async () => {
    server.use(
      http.get('*/api/v1/risk/assessments/:id', () => refuse(404, 'ASSESSMENT_NOT_FOUND')),
    );
    await openAgent('signals', '?as_of=2026-09-18');

    expect(await screen.findByText('The API has no such record any more.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Return to the inbox' })).toHaveAttribute(
      'href',
      '/classic/inbox?as_of=2026-09-18',
    );
  });

  it('loading while the inbox itself loads', async () => {
    server.use(http.get('*/api/v1/risk/assessments', hang));
    await openAgent('brief-writer');

    expect(screen.getByText('Loading the selected brief…')).toBeInTheDocument();
  });

  it('shows the API calls behind a panel', async () => {
    await openAgent('sales');
    await screen.findByRole('region', { name: 'SALES positions' });

    await userEvent.click(screen.getByText('Show the API call'));
    const table = screen.getByRole('table', { name: 'Requests behind this panel' });
    expect(
      within(table).getByText(/^GET \/api\/v1\/risk\/assessments\/[0-9a-f-]{36}$/),
    ).toBeInTheDocument();
  });
});
