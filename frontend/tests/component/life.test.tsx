/**
 * F4's page side (spec §9.4–§9.6, §9.12, R-F-6, R-F-7, D-F-1, AC-F-2; the owner's F4 ruling):
 * Run assessment as a show (live, hold, replay under its banner), Replay, the banner that ends a
 * replay, the Director's frames reaching the world and the staff directory, Run ingestion, the
 * decision stamp and sound.
 *
 * jsdom has no WebGL, so the world is a stub that records the props the page hands it.
 */

import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { COPY, fill } from '@/copy';
import type { IngestionRunCreatedResponse } from '@/api/schemas/operations';
import type { WorldAgent, WorldProps } from '@/office/worldTypes';
import { directorClock, useDirector } from '@/state/director';

import { answer, briefId, drop, flowExchange, hang, refuse } from '../support/api';
import { loadExchanges, type RecordedExchange } from '../support/fixtures';
import { renderRoute } from '../support/render';
import { server } from '../support/server';

const stub = vi.hoisted(() => ({ props: null as WorldProps | null }));
const sound = vi.hoisted(() => ({ clicks: 0, thumps: 0 }));

vi.mock('@/lib/webgl', () => ({ canCreateWebGL: () => true }));
vi.mock('@/lib/sound', () => ({
  keyClick: () => {
    sound.clicks += 1;
  },
  stampThump: () => {
    sound.thumps += 1;
  },
}));
vi.mock('@/world/Office', async () => {
  const { createElement } = await import('react');
  return {
    default: (props: WorldProps) => {
      stub.props = props;
      return createElement('div', { 'data-testid': 'world' });
    },
  };
});

beforeEach(() => {
  stub.props = null;
  sound.clicks = 0;
  sound.thumps = 0;
});

function props(): WorldProps {
  if (stub.props === null) throw new Error('the world has not rendered');
  return stub.props;
}

function agent(id: string): WorldAgent {
  const found = props().agents.find((world) => world.agent.id === id);
  if (found === undefined) throw new Error(`no agent ${id}`);
  return found;
}

function office() {
  return screen.getByTestId('office');
}

const [firstRun, repeatRun] = loadExchanges('assessment-runs.json') as [
  RecordedExchange,
  RecordedExchange,
];
const ingestionRun = loadExchanges('ingestion-run.json')[0] as RecordedExchange;
const created = ingestionRun.body as IngestionRunCreatedResponse;

/** Serve the assessment POST, held until `release` is called, and the run counts. */
function serveRun(exchange: RecordedExchange) {
  let release: () => void = () => undefined;
  const gate = new Promise<void>((done) => {
    release = done;
  });
  server.use(
    http.post('*/api/v1/risk/assessments', async () => {
      await gate;
      return answer(exchange, 'rid-run');
    }),
    http.get('*/api/v1/risk/assessments', ({ request }) => {
      if (new URL(request.url).searchParams.get('limit') !== '1') return undefined;
      return HttpResponse.json({ items: [], total: 50, limit: 1, offset: 0 });
    }),
  );
  return { release: () => release() };
}

/** Move the director's clock `seconds` on, and let the show catch up. */
function later(seconds: number) {
  const now = directorClock.now();
  directorClock.now = () => now + seconds * 1000;
  act(() => useDirector.getState().refresh());
}

async function openOffice(path = '/?as_of=2026-09-18') {
  const view = renderRoute(path);
  await screen.findByTestId('world');
  await waitFor(() => expect(props().trayCount).toBe(3));
  return view;
}

/** The replay banner; an open panel is modal, so the page behind it is hidden from roles. */
function banner() {
  return screen.queryByRole('status', { name: 'Replay', hidden: true });
}

describe('Run assessment in the office: a show (§9.6, AC-F-2)', () => {
  it('works while the POST is in flight, then replays the recorded results under the banner', async () => {
    const run = serveRun(firstRun);
    await openOffice();
    expect(office()).toHaveAttribute('data-show', 'none');
    expect(props().agents.some((world) => world.cue !== undefined)).toBe(false);

    await userEvent.click(screen.getByRole('button', { name: 'Run assessment' }));

    // Live: the stages light up in order, captioned ASSESSING…, and nothing else is shown.
    await waitFor(() => expect(office()).toHaveAttribute('data-show', 'live'));
    expect(agent('memory')).toMatchObject({
      state: 'WORKING',
      cue: { place: { kind: 'desk' }, caption: 'ASSESSING…' },
    });
    later(5);
    for (const id of [
      'memory',
      'linker',
      'signals',
      'sales',
      'support',
      'reconciler',
      'brief-writer',
    ])
      expect(agent(id).state).toBe('WORKING');
    expect(agent('csv_demo').cue).toBeUndefined();
    expect(agent('ceo').state).toBe('WAITING');
    expect(banner()).toBeNull();

    run.release();
    await waitFor(() => expect(office()).toHaveAttribute('data-show', 'replay'));
    expect(banner()).toHaveTextContent(fill(COPY.replayBanner, { date: '2026-09-18' }));
    // The gather: everyone at their desk, idle, and the tray empty until the deliveries.
    expect(agent('memory')).toMatchObject({ state: 'IDLE', cue: { place: { kind: 'desk' } } });
    expect(props().trayCount).toBe(0);
    expect(
      within(screen.getByRole('navigation', { name: 'Staff directory' })).getByRole('link', {
        name: /^MEMORY/,
      }),
    ).toHaveTextContent('Idle, at the desk');

    // The office does not cover the replay with the inbox; the status line links to it.
    const status = screen.getByRole('status', { name: 'Assessment run' });
    expect(status).toHaveTextContent('Assessed 50 customers');
    expect(screen.queryByRole('dialog', { name: 'CEO inbox' })).toBeNull();
    await userEvent.click(within(status).getByRole('link', { name: 'Show the inbox' }));
    expect(await screen.findByRole('dialog', { name: 'CEO inbox' })).toBeInTheDocument();
  });

  it('plays each step with its caption, hands results over, and ends with everyone idle', async () => {
    const run = serveRun(firstRun);
    await openOffice();
    await userEvent.click(screen.getByRole('button', { name: 'Run assessment' }));
    run.release();
    await waitFor(() => expect(office()).toHaveAttribute('data-show', 'replay'));

    const seen = new Map<string, Set<string>>();
    for (let step = 0; step < 200 && useDirector.getState().show !== null; step += 1) {
      for (const world of props().agents)
        if (world.cue?.caption != null)
          seen.set(world.agent.id, (seen.get(world.agent.id) ?? new Set()).add(world.cue.caption));
      if (props().arrows.length > 0) expect(props().arrows[0]?.label).toBeTruthy();
      later(0.5);
    }
    expect(useDirector.getState().show).toBeNull();
    expect(office()).toHaveAttribute('data-show', 'none');
    expect(banner()).toBeNull();
    expect(props().agents.some((world) => world.cue !== undefined)).toBe(false);
    expect(props().trayCount).toBe(3);
    expect([...(seen.get('memory') ?? [])][0]).toMatch(/^SNAPSHOT [0-9a-f]{8}$/);
    expect([...(seen.get('reconciler') ?? [])]).toContain('CONF-001 → SUPPORT PREVAILS');
    expect([...(seen.get('brief-writer') ?? [])]).toContain('BRIEF CUST-036');
  });

  it('says so when everything was already assessed (200)', async () => {
    const run = serveRun(repeatRun);
    await openOffice();
    await userEvent.click(screen.getByRole('button', { name: 'Run assessment' }));
    run.release();
    await waitFor(() => expect(banner()).toHaveTextContent(COPY.alreadyAssessedBanner));
  });

  it('ends the replay when its banner is dismissed, sending everyone back to the Break Area', async () => {
    const run = serveRun(firstRun);
    await openOffice();
    await userEvent.click(screen.getByRole('button', { name: 'Run assessment' }));
    run.release();
    await waitFor(() => expect(banner()).not.toBeNull());

    await userEvent.click(screen.getByRole('button', { name: 'End the replay' }));
    expect(banner()).toBeNull();
    expect(office()).toHaveAttribute('data-show', 'none');
    expect(props().agents.some((world) => world.cue !== undefined)).toBe(false);
    expect(props().arrows).toEqual([]);
  });

  it('stops the live show when the POST fails, and shows the failure', async () => {
    server.use(
      http.post('*/api/v1/risk/assessments', () => refuse(500, 'INTERNAL_ERROR')),
      http.get('*/api/v1/risk/assessments', ({ request }) =>
        new URL(request.url).searchParams.get('limit') === '1'
          ? HttpResponse.json({ items: [], total: 50, limit: 1, offset: 0 })
          : undefined,
      ),
    );
    await openOffice();
    await userEvent.click(screen.getByRole('button', { name: 'Run assessment' }));
    expect(await screen.findByRole('alert', { name: 'Assessment run' })).toHaveTextContent(
      'Nothing was written.',
    );
    expect(office()).toHaveAttribute('data-show', 'none');
  });

  it('ends the hold without a replay when the run’s data cannot be read', async () => {
    const run = serveRun(firstRun);
    await openOffice();
    // The run invalidates the list (§6.7), so the replay reads it again, and fails.
    server.use(
      http.get('*/api/v1/risk/assessments', ({ request }) =>
        new URL(request.url).searchParams.get('limit') === '1'
          ? HttpResponse.json({ items: [], total: 50, limit: 1, offset: 0 })
          : refuse(500, 'INTERNAL_ERROR'),
      ),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Run assessment' }));
    run.release();
    await waitFor(() =>
      expect(screen.getByRole('status', { name: 'Assessment run' })).toHaveTextContent('Assessed'),
    );
    await waitFor(() => expect(office()).toHaveAttribute('data-show', 'none'));
    expect(banner()).toBeNull();
  });

  it('forgets a chosen snapshot, so the office shows the run’s', async () => {
    const run = serveRun(firstRun);
    const { router } = await openOffice('/?as_of=2026-09-18&snapshot=1d891b0b543f');
    await userEvent.click(screen.getByRole('button', { name: 'Run assessment' }));
    run.release();
    await waitFor(() => expect(router.state.location.search).toBe('?as_of=2026-09-18'));
    expect(router.state.location.pathname).toBe('/');
  });
});

describe('Replay (§8.2, §9.5)', () => {
  it('replays the shown snapshot under the banner, and waits while a run is in flight', async () => {
    const run = serveRun(firstRun);
    await openOffice();
    const replay = within(screen.getByRole('banner')).getByRole('button', { name: 'Replay' });
    await waitFor(() => expect(replay).toBeEnabled());

    await userEvent.click(replay);
    await waitFor(() => expect(office()).toHaveAttribute('data-show', 'replay'));
    expect(banner()).toHaveTextContent(fill(COPY.replayBanner, { date: '2026-09-18' }));
    // Replay again: it starts over.
    await userEvent.click(replay);
    await waitFor(() => expect(office()).toHaveAttribute('data-show', 'replay'));

    await userEvent.click(screen.getByRole('button', { name: 'Run assessment' }));
    await waitFor(() => expect(office()).toHaveAttribute('data-show', 'live'));
    expect(replay).toBeDisabled();
    run.release();
    await waitFor(() => expect(office()).toHaveAttribute('data-show', 'replay'));
  });

  it('is not offered in Classic view, which has no office to play in', async () => {
    renderRoute('/classic?as_of=2026-09-18');
    await screen.findByRole('main');
    expect(within(screen.getByRole('banner')).queryByRole('button', { name: 'Replay' })).toBeNull();
    expect(within(screen.getByRole('banner')).queryByRole('button', { name: 'Sound' })).toBeNull();
  });

  it('plays nothing when the snapshot’s data cannot be read', async () => {
    const { client } = await openOffice();
    const replay = within(screen.getByRole('banner')).getByRole('button', { name: 'Replay' });
    await waitFor(() => expect(replay).toBeEnabled());
    // The inbox keeps what it shows; the replay reads the list afresh, and fails.
    await client.invalidateQueries({ queryKey: ['assessments'], refetchType: 'none' });
    server.use(http.get('*/api/v1/risk/assessments', () => refuse(500, 'INTERNAL_ERROR')));

    await userEvent.click(replay);
    // The failed read leaves the inbox in its error state, which Replay waits out.
    await waitFor(() => expect(replay).toBeDisabled());
    expect(office()).toHaveAttribute('data-show', 'none');
    expect(banner()).toBeNull();
  });
});

describe('Run assessment in Classic view', () => {
  it('opens the inbox and plays no show', async () => {
    const run = serveRun(firstRun);
    const { router } = renderRoute('/classic?as_of=2026-09-18');
    await screen.findByRole('main');
    await userEvent.click(screen.getByRole('button', { name: 'Run assessment' }));
    run.release();
    await waitFor(() => expect(router.state.location.pathname).toBe('/classic/inbox'));
    expect(useDirector.getState().show).toBeNull();
  });
});

describe('Run ingestion (R-F-6, R-F-7, §9.5)', () => {
  function serveIngestion(respond: () => Response | Promise<Response>, totals = [1, 1]) {
    const sent: unknown[] = [];
    let counted = 0;
    server.use(
      http.post('*/api/v1/ingestion/runs', async ({ request }) => {
        sent.push(await request.json());
        return respond();
      }),
      http.get('*/api/v1/ingestion/runs', ({ request }) => {
        if (new URL(request.url).searchParams.get('limit') !== '1') return undefined;
        const total = totals[Math.min(counted, totals.length - 1)] ?? 0;
        counted += 1;
        return HttpResponse.json({ items: [], total, limit: 1, offset: 0 });
      }),
    );
    return { sent };
  }

  async function openConnector(id: string) {
    renderRoute(`/?agent=${id}&as_of=2026-09-18`);
    const drawer = await screen.findByRole('dialog', { name: `${id.toUpperCase()}_AGENT` });
    return within(drawer).findByRole('region', { name: 'Run ingestion' });
  }

  it('sends the source only, reports the run’s own outcome, and replays it in the office', async () => {
    const { sent } = serveIngestion(() => answer(ingestionRun, 'rid-ingest'));
    const section = await openConnector('csv_demo');
    const button = within(section).getByRole('button', { name: 'Run ingestion' });
    await waitFor(() => expect(button).toBeEnabled());

    await userEvent.click(button);
    const outcome = await within(section).findByRole('status', { name: 'Ingestion run' });
    expect(sent).toEqual([{ source: 'csv_demo' }]);
    expect(outcome).toHaveTextContent(`finished ${created.status}`);
    expect(outcome).toHaveTextContent('so nothing changed.');
    expect(within(outcome).getAllByRole('row')).toHaveLength(created.entities.length + 1);

    await waitFor(() => expect(office()).toHaveAttribute('data-show', 'replay'));
    expect(banner()).toHaveTextContent(
      fill(COPY.replayBanner, { date: created.started_at.slice(0, 10) }),
    );
    const cast = [...(useDirector.getState().frame?.directives.keys() ?? [])];
    expect(cast).toEqual(['csv_demo', 'memory']);
  });

  it('is enabled only while the source is healthy', async () => {
    serveIngestion(() => answer(ingestionRun, 'rid-ingest'));
    const section = await openConnector('odoo_mock');
    const button = within(section).getByRole('button', { name: 'Run ingestion' });
    await waitFor(() =>
      expect(section).toHaveTextContent(
        "Enabled only while this source's health check says healthy.",
      ),
    );
    expect(button).toBeDisabled();
  });

  it('says a refusal created no run', async () => {
    serveIngestion(() => refuse(422, 'SOURCE_NOT_FOUND', null, 'rid-422'));
    const section = await openConnector('csv_demo');
    const button = within(section).getByRole('button', { name: 'Run ingestion' });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    const alert = await within(section).findByRole('alert', { name: 'Ingestion run' });
    expect(alert).toHaveTextContent('No run was created.');
    expect(alert).toHaveTextContent('request rid-422');
    expect(useDirector.getState().show).toBeNull();
  });

  it('re-reads after a 500, which may have left a FAILED run, and after no answer', async () => {
    serveIngestion(() => refuse(500, 'INTERNAL_ERROR'), [1, 2]);
    const section = await openConnector('csv_demo');
    const button = within(section).getByRole('button', { name: 'Run ingestion' });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    const status = () => within(section).getByRole('status', { name: 'Ingestion run' });
    await waitFor(() => expect(status()).toHaveTextContent('The ingestion was recorded'));

    serveIngestion(drop, [1, 1]);
    await userEvent.click(button);
    await waitFor(() =>
      expect(status()).toHaveTextContent('No new run was recorded, so running it again is safe.'),
    );
    serveIngestion(() => answer(ingestionRun, 'rid-ingest'));
    await userEvent.click(within(section).getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(status()).toHaveTextContent('finished'));
  });

  it('offers Check again when the re-read fails too, and nothing when the count fails first', async () => {
    let counts = 0;
    server.use(
      http.post('*/api/v1/ingestion/runs', drop),
      http.get('*/api/v1/ingestion/runs', ({ request }) => {
        if (new URL(request.url).searchParams.get('limit') !== '1') return undefined;
        counts += 1;
        return counts === 1
          ? HttpResponse.json({ items: [], total: 1, limit: 1, offset: 0 })
          : refuse(503, 'UNAVAILABLE');
      }),
    );
    const section = await openConnector('csv_demo');
    const button = within(section).getByRole('button', { name: 'Run ingestion' });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await within(section).findByRole('alert', { name: 'Ingestion run' })).toHaveTextContent(
      'the result is still unknown',
    );
    server.use(
      http.get('*/api/v1/ingestion/runs', ({ request }) =>
        new URL(request.url).searchParams.get('limit') === '1'
          ? HttpResponse.json({ items: [], total: 2, limit: 1, offset: 0 })
          : undefined,
      ),
    );
    await userEvent.click(within(section).getByRole('button', { name: 'Check again' }));
    expect(await within(section).findByRole('status', { name: 'Ingestion run' })).toHaveTextContent(
      'The ingestion was recorded',
    );

    server.use(http.get('*/api/v1/ingestion/runs', () => refuse(503, 'UNAVAILABLE')));
    await userEvent.click(button);
    expect(await within(section).findByRole('alert', { name: 'Ingestion run' })).toHaveTextContent(
      'The ingestion was not sent',
    );
  });

  it('shows the unknown-outcome message while it re-reads', async () => {
    let counts = 0;
    server.use(
      http.post('*/api/v1/ingestion/runs', drop),
      http.get('*/api/v1/ingestion/runs', ({ request }) => {
        if (new URL(request.url).searchParams.get('limit') !== '1') return undefined;
        counts += 1;
        return counts === 1
          ? HttpResponse.json({ items: [], total: 1, limit: 1, offset: 0 })
          : hang();
      }),
    );
    const section = await openConnector('csv_demo');
    const button = within(section).getByRole('button', { name: 'Run ingestion' });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await within(section).findByRole('status', { name: 'Ingestion run' })).toHaveTextContent(
      COPY.unknownOutcome,
    );
    expect(button).toBeDisabled();
  });
});

describe('the decision stamp (§9.5)', () => {
  it('stamps an approval on the CEO’s desk, once per decision', async () => {
    const approval = flowExchange(
      (item) => item.method === 'POST' && item.status === 201 && item.path.includes(briefId(0)),
    );
    server.use(
      http.post(`*/api/v1/risk/briefs/${briefId(0)}/decision`, () =>
        answer(approval, 'rid-approve'),
      ),
    );
    renderRoute(`/brief/${briefId(0)}?as_of=2026-09-18`);
    const overlay = await screen.findByRole('dialog', { name: 'Brief' });
    const form = await within(overlay).findByRole('form', { name: 'Record a decision' });
    await userEvent.click(within(form).getByText('Approve'));
    await userEvent.type(within(form).getByLabelText(/Your name/), 'Test Owner');
    await userEvent.click(within(form).getByRole('button', { name: 'Record decision' }));

    await waitFor(() => expect(props().stamp).toEqual({ id: 1, decision: 'APPROVED' }));
    expect(sound.thumps).toBe(0);
  });
});

describe('sound (§9.12, D-F-19)', () => {
  it('is off by default, remembered when on, and clicks only while someone works', async () => {
    const run = serveRun(firstRun);
    await openOffice();
    const toggle = within(screen.getByRole('banner')).getByRole('button', { name: 'Sound' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(window.localStorage.getItem('aiceohq.sound')).toBe('1');

    await userEvent.click(screen.getByRole('button', { name: 'Run assessment' }));
    await waitFor(() => expect(sound.clicks).toBeGreaterThan(0));
    run.release();
    await waitFor(() => expect(office()).toHaveAttribute('data-show', 'replay'));

    act(() => useDirector.getState().stampDecision('REJECTED'));
    expect(sound.thumps).toBe(1);
    await userEvent.click(toggle);
    act(() => useDirector.getState().stampDecision('APPROVED'));
    expect(sound.thumps).toBe(1);
  });
});
