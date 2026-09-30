/**
 * The office page (spec §8.1–§8.5, §9, §10, §11): its model from the recorded fixtures, the staff
 * directory, the panels as drawers and the brief overlay, the view and pixel switches, the camera
 * controls, the evidence highlight and the WebGL fallback (§9.11).
 *
 * jsdom has no WebGL, so the 3D world is replaced by a stub that records the props the page hands
 * it, and the WebGL probe is controlled by the test. The e2e tests draw the real world.
 */

import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { COPY, ROLE_LINES } from '@/copy';
import { HIGHLIGHT_MS } from '@/office/OfficePage';
import type { WorldProps } from '@/office/worldTypes';
import { useCamera } from '@/state/camera';
import { useSession } from '@/state/session';

import { briefBodies, briefId, flowExchange, hang, refuse } from '../support/api';
import { recordedBody } from '../support/fixtures';
import { renderRoute } from '../support/render';
import { answer, server } from '../support/server';

const stub = vi.hoisted(() => ({
  webgl: true,
  fail: false,
  props: null as WorldProps | null,
}));

vi.mock('@/lib/webgl', () => ({ canCreateWebGL: () => stub.webgl }));

vi.mock('@/world/Office', async () => {
  const { createElement } = await import('react');
  return {
    default: (props: WorldProps) => {
      stub.props = props;
      if (stub.fail) throw new Error('WebGL could not start');
      return createElement('div', { 'data-testid': 'world' });
    },
  };
});

beforeEach(() => {
  stub.webgl = true;
  stub.fail = false;
  stub.props = null;
});

afterEach(() => {
  vi.useRealTimers();
});

function props(): WorldProps {
  if (stub.props === null) throw new Error('the world has not rendered');
  return stub.props;
}

async function openOffice(path = '/') {
  const view = renderRoute(path);
  await screen.findByTestId('world');
  return view;
}

function directory() {
  return screen.getByRole('navigation', { name: 'Staff directory' });
}

function office() {
  return screen.getByTestId('office');
}

const detail = recordedBody<{ customer_source_id: string; signals: Record<string, unknown> }>(
  'assessment-details.json',
  'GET',
  `/api/v1/risk/assessments/${briefBodies()[0]?.assessment_id ?? ''}`,
);

describe('the office at / (D-F-6, §9.2)', () => {
  it('is the home screen: the world, the staff directory and the view controls', async () => {
    const { router } = await openOffice('/?as_of=2026-09-18');

    expect(router.state.location.pathname).toBe('/');
    expect(screen.getByRole('region', { name: '3D office' })).toBeInTheDocument();
    expect(screen.getByRole('toolbar', { name: 'View controls' })).toBeInTheDocument();
    const links = within(directory()).getAllByRole('link');
    expect(links[0]).toHaveTextContent('CEO inbox');
    expect(links[0]).toHaveAttribute('href', '/?as_of=2026-09-18&inbox=1');
    expect(within(directory()).getByText(COPY.aboutAgents)).toBeInTheDocument();
    await within(directory()).findByText('REST_MOCK_AGENT');
    expect(within(directory()).getAllByRole('link')).toHaveLength(12);
  });

  it("hands the world every agent's state, from the requests behind its panel", async () => {
    await openOffice();

    await waitFor(() => expect(props().agents).toHaveLength(11));
    await waitFor(() =>
      expect(
        Object.fromEntries(props().agents.map((world) => [world.agent.id, world.detail])),
      ).toEqual({
        csv_demo: 'Idle',
        odoo_mock: 'Its source reports unhealthy.',
        rest_mock: 'Its source reports unhealthy.',
        memory: 'Idle',
        linker: 'Idle',
        signals: 'Idle',
        sales: 'Idle',
        support: 'Idle',
        reconciler: 'Idle',
        'brief-writer': 'Idle',
        ceo: '3 briefs await your decision',
      }),
    );
    const states = Object.fromEntries(props().agents.map((world) => [world.agent.id, world.state]));
    expect(states).toMatchObject({ odoo_mock: 'ERROR', ceo: 'WAITING', linker: 'IDLE' });
    expect(props().agents.find((world) => world.agent.id === 'ceo')?.bubble).toBe('waiting');
    expect(props().agents.some((world) => world.state === 'WORKING')).toBe(false);

    const entry = within(directory()).getByRole('link', { name: /ODOO_MOCK_AGENT/ });
    expect(entry).toHaveTextContent('Its source reports unhealthy.');
    expect(entry.querySelector('[data-bulb="error"]')).toHaveTextContent('!');
  });

  it("draws SIGNALS_AGENT's board and the tray from the selected brief, and mirrors them in text", async () => {
    await openOffice();

    await waitFor(() => expect(props().board.kind).toBe('ready'));
    const board = props().board;
    if (board.kind !== 'ready') throw new Error('the board is not ready');
    expect(board.board.title).toBe(`SIGNALS ${detail.customer_source_id}`);
    expect(board.board.footer).toBe('BAND CRITICAL');
    expect(props().trayCount).toBe(3);
    expect(props().notes).toEqual([]);

    const mirror = screen.getByRole('region', { name: "SIGNALS_AGENT's board" });
    expect(within(mirror).getByText(`SIGNALS ${detail.customer_source_id}`)).toBeInTheDocument();
    expect(
      within(mirror).getByText(
        `S1 open_ticket_count: ${String(detail.signals['open_ticket_count'])}`,
      ),
    ).toBeInTheDocument();
    expect(within(mirror).getAllByRole('listitem')).toHaveLength(14);
    expect(
      within(screen.getByRole('region', { name: "The CEO's corkboard" })).getByText(
        'No decision is pinned for the selected brief.',
      ),
    ).toBeInTheDocument();
  });

  it('pins one note per decision on the selected brief', async () => {
    const chain = flowExchange(
      (item) => item.method === 'GET' && item.path.endsWith(`/${briefId(0)}/decisions`),
    );
    server.use(
      http.get(`*/api/v1/risk/briefs/${briefId(0)}/decisions`, () => answer(chain, 'rid-chain')),
    );
    await openOffice();

    await waitFor(() =>
      expect(props().notes).toEqual([
        { ordinal: 1, decision: 'APPROVED' },
        { ordinal: 2, decision: 'REJECTED' },
      ]),
    );
    const corkboard = screen.getByRole('region', { name: "The CEO's corkboard" });
    expect(within(corkboard).getByText('Decision 2: REJECTED')).toBeInTheDocument();
  });

  it('shows the loading bubble while the data loads, and ERROR when a request fails', async () => {
    server.use(
      http.get('*/api/v1/health', () => refuse(404, 'NOT_FOUND', null, 'rid-down')),
      http.get('*/api/v1/risk/assessments', hang),
    );
    await openOffice();

    await waitFor(() => {
      const memory = props().agents.find((world) => world.agent.id === 'memory');
      expect(memory?.state).toBe('ERROR');
    });
    const linker = props().agents.find((world) => world.agent.id === 'linker');
    expect(linker).toMatchObject({ state: 'IDLE', bubble: 'loading' });
    expect(props().board).toEqual({ kind: 'loading' });
    expect(props().trayCount).toBeNull();
    const memory = props().agents.find((world) => world.agent.id === 'memory');
    expect(memory?.detail).toContain('NOT_FOUND');
    expect(screen.getByRole('region', { name: "SIGNALS_AGENT's board" })).toHaveTextContent(
      'The board is loading.',
    );
  });

  it('says the board is blank when there is no brief, and when its assessment fails', async () => {
    server.use(
      http.get(`*/api/v1/risk/assessments/:id`, () => refuse(404, 'ASSESSMENT_NOT_FOUND')),
    );
    const { unmount } = await openOffice();
    await waitFor(() => expect(props().board).toEqual({ kind: 'error' }));
    expect(screen.getByRole('region', { name: "SIGNALS_AGENT's board" })).toHaveTextContent(
      'its assessment could not be read',
    );
    unmount();

    server.use(
      http.get('*/api/v1/risk/assessments', () =>
        HttpResponse.json({ items: [], total: 0, limit: 500, offset: 0 }),
      ),
    );
    await openOffice('/?as_of=2026-01-01');
    await waitFor(() => expect(props().board).toEqual({ kind: 'empty' }));
    expect(props().trayCount).toBe(0);
    expect(props().agents.find((world) => world.agent.id === 'ceo')?.detail).toBe('Idle');
  });
});

describe('panels as drawers (§8.3, §10)', () => {
  it('opens an agent from the staff directory, and returns focus when it closes', async () => {
    const { router } = await openOffice('/?as_of=2026-09-18');
    const entry = await within(directory()).findByRole('link', { name: /^MEMORY/ });

    await userEvent.click(entry);

    expect(router.state.location.search).toBe('?as_of=2026-09-18&agent=memory');
    const drawer = await screen.findByRole('dialog', { name: 'MEMORY' });
    expect(within(drawer).getByText(ROLE_LINES.memory)).toBeInTheDocument();
    expect(await within(drawer).findByText('Canonical records')).toBeInTheDocument();
    expect(props().openAgentId).toBe('memory');
    expect(entry).toHaveAttribute('aria-current', 'true');

    await userEvent.keyboard('{Escape}');

    await waitFor(() => expect(router.state.location.search).toBe('?as_of=2026-09-18'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(entry).toHaveFocus());
  });

  it('opens a deep-linked agent, and gives focus back to the office when it closes', async () => {
    const { router } = await openOffice('/?agent=reconciler');

    const drawer = await screen.findByRole('dialog', { name: 'RECONCILER_AGENT' });
    await userEvent.click(within(drawer).getByRole('button', { name: 'Close' }));

    await waitFor(() => expect(router.state.location.search).toBe(''));
    await waitFor(() => expect(screen.getByRole('region', { name: '3D office' })).toHaveFocus());
  });

  it('says so for an agent that does not work here, once the roster has loaded', async () => {
    await openOffice('/?agent=nobody');

    const drawer = await screen.findByRole('dialog', { name: 'Agent' });
    expect(
      await within(drawer).findByText('No agent named nobody works in this office.'),
    ).toBeInTheDocument();
  });

  it('waits for the roster before judging an unknown agent', async () => {
    server.use(http.get('*/api/v1/sources', hang));
    await openOffice('/?agent=csv_demo');

    const drawer = await screen.findByRole('dialog', { name: 'Agent' });
    expect(within(drawer).getByText('Loading the agent roster…')).toBeInTheDocument();
  });

  it('opens the CEO inbox, and a brief over the office from it', async () => {
    const { router } = await openOffice('/?inbox=1&as_of=2026-09-18');

    const inbox = await screen.findByRole('dialog', { name: 'CEO inbox' });
    expect(within(inbox).getByText(ROLE_LINES.ceo)).toBeInTheDocument();
    const rows = await within(inbox).findAllByTestId('inbox-row');
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveAttribute('href', `/brief/${briefId(0)}?as_of=2026-09-18`);
    expect(props().openAgentId).toBe('ceo');

    await userEvent.click(rows[0] as HTMLElement);

    expect(router.state.location.pathname).toBe(`/brief/${briefId(0)}`);
    const overlay = await screen.findByRole('dialog', { name: 'Brief' });
    expect(await within(overlay).findByRole('region', { name: 'Technical' })).toBeInTheDocument();
    expect(screen.getByTestId('world')).toBeInTheDocument();

    await userEvent.click(within(overlay).getByRole('button', { name: 'Close' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(router.state.location.search).toBe('?as_of=2026-09-18');
  });

  it("keeps panel links in the office: a brief's not-found state leads to the office inbox", async () => {
    const missing = '00000000-0000-4000-8000-000000000000';
    server.use(
      http.get(`*/api/v1/risk/briefs/${missing}`, () => refuse(404, 'BRIEF_NOT_FOUND')),
      http.get(`*/api/v1/risk/briefs/${missing}/decisions`, () => refuse(404, 'BRIEF_NOT_FOUND')),
    );
    await openOffice(`/brief/${missing}?as_of=2026-09-18`);

    const overlay = await screen.findByRole('dialog', { name: 'Brief' });
    const back = await within(overlay).findByRole('link', { name: /inbox/i });
    expect(back).toHaveAttribute('href', '/?as_of=2026-09-18&inbox=1');
  });

  it('shows the selected brief in agent panels, linking to it over the office', async () => {
    await openOffice('/?agent=linker&as_of=2026-09-18');

    const drawer = await screen.findByRole('dialog', { name: 'LINKER_AGENT' });
    const link = await within(drawer).findByRole('link', { name: 'Meridian Textiles' });
    expect(link).toHaveAttribute('href', `/brief/${briefId(0)}?as_of=2026-09-18`);
  });

  it('opens what the world asks for', async () => {
    const { router } = await openOffice('/?pixel=0');

    act(() => props().onOpenAgent('signals'));
    expect(router.state.location.search).toBe('?pixel=0&agent=signals');
    act(() => props().onOpenInbox());
    expect(router.state.location.search).toBe('?pixel=0&inbox=1');
  });
});

describe('the evidence highlight (§8.4)', () => {
  it("highlights SUPPORT_AGENT's desk for a ticket and LINKER_AGENT's for a document, for a while", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
    await openOffice(`/brief/${briefId(0)}?as_of=2026-09-18`);
    const overlay = await screen.findByRole('dialog', { name: 'Brief' });
    const tickets = await within(overlay).findByRole('region', { name: 'Evidence: tickets' });

    await user.click(
      within(tickets).getAllByRole('button', { name: /created_at$/ })[0] as HTMLElement,
    );
    expect(office()).toHaveAttribute('data-highlight', 'support');
    expect(props().highlightedAgentId).toBe('support');
    await user.keyboard('{Escape}');

    const quotes = within(overlay).getByRole('region', { name: 'Evidence: cited quotes' });
    await user.click(
      within(quotes).getAllByRole('button', { name: /^DOC-\d{3} \[/ })[0] as HTMLElement,
    );
    expect(office()).toHaveAttribute('data-highlight', 'linker');

    act(() => {
      vi.advanceTimersByTime(HIGHLIGHT_MS);
    });
    expect(office()).toHaveAttribute('data-highlight', '');
  });

  it('highlights nothing in Classic view', async () => {
    renderRoute(`/classic/briefs/${briefId(0)}?as_of=2026-09-18`);
    const tickets = await screen.findByRole('region', { name: 'Evidence: tickets' });

    await userEvent.click(
      within(tickets).getAllByRole('button', { name: /created_at$/ })[0] as HTMLElement,
    );

    expect(useSession.getState().highlightedAgentId).toBeNull();
  });
});

describe('the view controls (§9.8)', () => {
  it('turns, zooms and resets from the toolbar and the keys', async () => {
    await openOffice();
    const toolbar = screen.getByRole('toolbar', { name: 'View controls' });
    expect(office()).toHaveAttribute('data-yaw', '45');
    expect(within(toolbar).getByRole('button', { name: 'Zoom out (minus)' })).toBeDisabled();

    await userEvent.click(within(toolbar).getByRole('button', { name: 'Turn right (E)' }));
    expect(office()).toHaveAttribute('data-yaw', '135');
    await userEvent.click(within(toolbar).getByRole('button', { name: 'Turn left (Q)' }));
    await userEvent.click(within(toolbar).getByRole('button', { name: 'Turn left (Q)' }));
    expect(office()).toHaveAttribute('data-yaw', '315');
    await userEvent.click(within(toolbar).getByRole('button', { name: 'Zoom in (plus)' }));
    await userEvent.click(within(toolbar).getByRole('button', { name: 'Zoom in (plus)' }));
    expect(office()).toHaveAttribute('data-zoom', '2');
    expect(within(toolbar).getByRole('button', { name: 'Zoom in (plus)' })).toBeDisabled();

    await userEvent.click(within(toolbar).getByRole('button', { name: 'Reset the view (0)' }));
    expect(office()).toHaveAttribute('data-yaw', '45');
    expect(office()).toHaveAttribute('data-zoom', '0');

    act(() => screen.getByRole('region', { name: '3D office' }).focus());
    await userEvent.keyboard('e+');
    expect(office()).toHaveAttribute('data-yaw', '135');
    expect(office()).toHaveAttribute('data-zoom', '1');
    await userEvent.keyboard('Q-0');
    expect(office()).toHaveAttribute('data-yaw', '45');
    expect(office()).toHaveAttribute('data-zoom', '0');

    const before = useCamera.getState().target;
    await userEvent.keyboard('{ArrowRight}{ArrowDown}');
    expect(useCamera.getState().target).not.toEqual(before);
    await userEvent.keyboard('{Control>}e{/Control}x');
    expect(office()).toHaveAttribute('data-yaw', '45');
  });

  it('leaves the keys alone in a field and in an open panel', async () => {
    await openOffice('/?agent=memory');
    await screen.findByRole('dialog', { name: 'MEMORY' });

    await userEvent.keyboard('e');
    expect(office()).toHaveAttribute('data-yaw', '45');
  });

  it('pans with a drag and zooms with the wheel', async () => {
    await openOffice();
    const viewport = screen.getByRole('region', { name: '3D office' });
    useCamera.setState({ pixelsPerUnit: 20 });
    const before = useCamera.getState().target;

    await userEvent.pointer([
      { keys: '[MouseLeft>]', target: viewport, coords: { clientX: 100, clientY: 100 } },
      { target: viewport, coords: { clientX: 140, clientY: 100 } },
      { keys: '[/MouseLeft]', target: viewport },
    ]);
    const dragged = useCamera.getState().target;
    expect(dragged).not.toEqual(before);
    await userEvent.pointer({ target: viewport, coords: { clientX: 300, clientY: 100 } });
    expect(useCamera.getState().target).toEqual(dragged);

    act(() => {
      viewport.dispatchEvent(new WheelEvent('wheel', { deltaY: -50, bubbles: true }));
    });
    expect(office()).toHaveAttribute('data-zoom', '0');
    act(() => {
      viewport.dispatchEvent(new WheelEvent('wheel', { deltaY: -50, bubbles: true }));
    });
    expect(office()).toHaveAttribute('data-zoom', '1');
    act(() => {
      viewport.dispatchEvent(new WheelEvent('wheel', { deltaY: 100, bubbles: true }));
    });
    expect(office()).toHaveAttribute('data-zoom', '0');
  });
});

describe('the view and pixel switches (§8.2, §11)', () => {
  it('switches to the Classic twin of the address and remembers the choice', async () => {
    const { router } = await openOffice('/?as_of=2026-09-18&still=1');
    const views = screen.getByRole('navigation', { name: 'View' });
    expect(within(views).getByRole('link', { name: 'Office' })).toHaveAttribute(
      'aria-current',
      'page',
    );

    await userEvent.click(within(views).getByRole('link', { name: 'Classic' }));

    expect(router.state.location.pathname).toBe('/classic');
    expect(router.state.location.search).toBe('?as_of=2026-09-18');
    expect(window.localStorage.getItem('aiceohq.view')).toBe('classic');
    expect(screen.queryByRole('group', { name: 'Rendering' })).not.toBeInTheDocument();
  });

  it('sends a reader who chose Classic there from /, without the WebGL notice', async () => {
    window.localStorage.setItem('aiceohq.view', 'classic');
    const { router } = renderRoute('/?inbox=1');

    await waitFor(() => expect(router.state.location.pathname).toBe('/classic/inbox'));
    expect(screen.queryByText(COPY.webglFallback)).not.toBeInTheDocument();
  });

  it('switches back to the office twin, and remembers that too', async () => {
    window.localStorage.setItem('aiceohq.view', 'classic');
    const { router } = renderRoute(`/classic/briefs/${briefId(0)}`);
    const views = screen.getByRole('navigation', { name: 'View' });

    await userEvent.click(within(views).getByRole('link', { name: 'Office' }));

    expect(router.state.location.pathname).toBe(`/brief/${briefId(0)}`);
    expect(window.localStorage.getItem('aiceohq.view')).toBe('office');
    await screen.findByTestId('world');
  });

  it('switches between pixel art and smooth toon, remembering the choice', async () => {
    const { router } = await openOffice();
    const group = screen.getByRole('group', { name: 'Rendering' });
    expect(within(group).getByRole('button', { name: 'Pixel' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(props().pixel).toBe(true);
    expect(office()).toHaveAttribute('data-pixel', '1');

    await userEvent.click(within(group).getByRole('button', { name: 'Smooth' }));

    expect(within(group).getByRole('button', { name: 'Smooth' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(props().pixel).toBe(false);
    expect(window.localStorage.getItem('aiceohq.pixel')).toBe('0');
    expect(router.state.location.search).toBe('');
  });

  it('lets ?pixel=0 choose smooth, and clears it when the reader chooses', async () => {
    const { router } = await openOffice('/?pixel=0&as_of=2026-09-18');
    const group = screen.getByRole('group', { name: 'Rendering' });
    expect(within(group).getByRole('button', { name: 'Smooth' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    await userEvent.click(within(group).getByRole('button', { name: 'Pixel' }));

    expect(router.state.location.search).toBe('?as_of=2026-09-18');
    expect(props().pixel).toBe(true);
  });

  it('passes still and perf to the world, and the product name leads home in each view', async () => {
    await openOffice('/?still=1&perf=1');
    expect(props()).toMatchObject({ still: true, perf: true, reducedMotion: false });
    expect(screen.getByRole('link', { name: COPY.productName })).toHaveAttribute(
      'href',
      '/?still=1&perf=1',
    );
  });
});

describe('the WebGL fallback (§9.11, AC-F-8)', () => {
  it('opens the Classic twin with the notice when WebGL cannot start', async () => {
    stub.webgl = false;
    const { router } = renderRoute('/?agent=linker&as_of=auto&pixel=0');

    await waitFor(() => expect(router.state.location.pathname).toBe('/classic/agents/linker'));
    expect(router.state.location.search).toBe('?as_of=auto');
    expect(await screen.findByText(COPY.webglFallback)).toBeInTheDocument();
    expect(screen.queryByTestId('world')).not.toBeInTheDocument();
  });

  it('falls back when the world fails, and stays in Classic for the session', async () => {
    stub.fail = true;
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { router } = renderRoute(`/brief/${briefId(0)}`);

    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/classic/briefs/${briefId(0)}`),
    );
    expect(await screen.findByText(COPY.webglFallback)).toBeInTheDocument();
    expect(useSession.getState().webglFailed).toBe(true);

    stub.fail = false;
    await act(() => router.navigate('/'));
    await waitFor(() => expect(router.state.location.pathname).toBe('/classic'));
  });

  it('survives one lost WebGL context and falls back on the second', async () => {
    const { router } = await openOffice();

    act(() => props().onContextLost());
    expect(router.state.location.pathname).toBe('/');
    act(() => props().onContextLost());

    await waitFor(() => expect(router.state.location.pathname).toBe('/classic'));
    expect(await screen.findByText(COPY.webglFallback)).toBeInTheDocument();
  });

  it('marks the world ready once it has drawn its first frame', async () => {
    await openOffice();
    expect(office()).toHaveAttribute('data-world', 'loading');
    act(() => props().onReady());
    expect(office()).toHaveAttribute('data-world', 'ready');
  });
});
