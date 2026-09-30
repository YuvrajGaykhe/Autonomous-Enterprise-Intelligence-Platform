/**
 * F6's surfaces: the three-step tour (§8.2), phones sent to Classic view (§14 F6), and the pixel
 * art on the main empty states and the office's loading screen.
 *
 * jsdom has no WebGL and no `matchMedia`, so the world is a stub, the WebGL probe says yes, and the
 * window's width is a media query the test controls.
 */

import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { COPY } from '@/copy';
import { TOUR_SEEN } from '@/domain/tour';
import { STORAGE_KEYS } from '@/lib/storage';
import { useSession } from '@/state/session';
import { LoadingArt } from '@/states/states';

import { briefId, refuse } from '../support/api';
import { renderRoute } from '../support/render';
import { server } from '../support/server';

const stub = vi.hoisted(() => ({ rendered: false }));

vi.mock('@/lib/webgl', () => ({ canCreateWebGL: () => true }));

vi.mock('@/world/Office', async () => {
  const { createElement } = await import('react');
  return {
    default: () => {
      stub.rendered = true;
      return createElement('div', { 'data-testid': 'world' });
    },
  };
});

/** The window's width as the office's media query sees it. */
const media = { wide: true, listeners: new Set<() => void>() };

beforeEach(() => {
  stub.rendered = false;
  media.wide = true;
  media.listeners.clear();
  window.matchMedia = (query: string) =>
    ({
      media: query,
      matches: query.includes('min-width') ? media.wide : false,
      addEventListener: (_: string, listener: () => void) => media.listeners.add(listener),
      removeEventListener: (_: string, listener: () => void) => media.listeners.delete(listener),
    }) as unknown as MediaQueryList;
});

afterEach(() => {
  Reflect.deleteProperty(window, 'matchMedia');
});

function narrowTo(wide: boolean) {
  media.wide = wide;
  act(() => media.listeners.forEach((listener) => listener()));
}

/** A first visit: nothing in storage says the tour was seen. */
function firstVisit() {
  window.localStorage.removeItem(STORAGE_KEYS.tour);
}

function tour() {
  return screen.getByRole('dialog', { name: /Meet the agents|Watch a run|Decide as the CEO/ });
}

function spots() {
  return [...document.querySelectorAll('[data-tour-spot="on"]')];
}

describe('the tour (§8.2, F6)', () => {
  it('opens on a first visit to Classic view and walks through its three steps', async () => {
    firstVisit();
    renderRoute('/classic');

    expect(await screen.findByRole('dialog', { name: 'Meet the agents' })).toBeInTheDocument();
    expect(within(tour()).getByText('Tour · step 1 of 3')).toBeInTheDocument();
    expect(within(tour()).getByText(/rule-based components/)).toBeInTheDocument();
    expect(spots()).toEqual([document.querySelector('ul[aria-label="Staff directory"]')]);
    expect(within(tour()).getByRole('button', { name: 'Next' })).toHaveFocus();

    await userEvent.click(within(tour()).getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('dialog', { name: 'Watch a run' })).toBeInTheDocument();
    expect(spots()).toHaveLength(1);
    expect(
      within(spots()[0] as HTMLElement).getByRole('button', {
        name: 'Run assessment',
        hidden: true,
      }),
    ).toBeInTheDocument();

    await userEvent.click(within(tour()).getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('dialog', { name: 'Decide as the CEO' })).toBeInTheDocument();
    expect(within(tour()).getByText(/nothing is executed/)).toBeInTheDocument();
    expect(spots()).toHaveLength(1);
    expect(spots()[0]).toHaveTextContent('CEO inbox');
    expect(within(tour()).getByRole('button', { name: 'Start exploring' })).toHaveFocus();

    await userEvent.click(within(tour()).getByRole('button', { name: 'Back' }));
    expect(screen.getByRole('dialog', { name: 'Watch a run' })).toBeInTheDocument();
    await userEvent.click(within(tour()).getByRole('button', { name: 'Next' }));
    await userEvent.click(within(tour()).getByRole('button', { name: 'Start exploring' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(spots()).toEqual([]);
    expect(window.localStorage.getItem(STORAGE_KEYS.tour)).toBe(TOUR_SEEN);
  });

  it("points at the office's own staff directory and CEO inbox entry", async () => {
    firstVisit();
    renderRoute('/');

    await screen.findByRole('dialog', { name: 'Meet the agents' });
    expect(spots()).toEqual([document.querySelector('nav[aria-label="Staff directory"]')]);
    await userEvent.click(within(tour()).getByRole('button', { name: 'Next' }));
    await userEvent.click(within(tour()).getByRole('button', { name: 'Next' }));
    expect(spots()).toHaveLength(1);
    expect(spots()[0]).toHaveAttribute('href', '/?inbox=1');
    expect(spots()[0]).toHaveTextContent('CEO inbox');
  });

  it('does not interrupt a reader who arrives on a deep link', async () => {
    firstVisit();
    renderRoute('/classic/inbox');

    await screen.findByRole('heading', { name: 'CEO inbox' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('stays closed for a reader who has seen it, until the HUD opens it again', async () => {
    renderRoute('/classic');
    await screen.findByRole('heading', { name: 'Overview' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Tour' }));
    expect(screen.getByRole('dialog', { name: 'Meet the agents' })).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Tour' })).toHaveFocus());
    expect(window.localStorage.getItem(STORAGE_KEYS.tour)).toBe(TOUR_SEEN);
  });

  it('closes from its close button and opens again at the first step', async () => {
    renderRoute('/classic');
    await userEvent.click(await screen.findByRole('button', { name: 'Tour' }));
    await userEvent.click(within(tour()).getByRole('button', { name: 'Next' }));
    await userEvent.click(within(tour()).getByRole('button', { name: 'Close the tour' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Tour' }));
    expect(screen.getByRole('dialog', { name: 'Meet the agents' })).toBeInTheDocument();
  });

  it('opens again on every visit when storage is unavailable', async () => {
    firstVisit();
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage is disabled');
    });
    try {
      renderRoute('/classic');
      await userEvent.click(
        within(await screen.findByRole('dialog')).getByRole('button', { name: 'Close the tour' }),
      );
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(window.localStorage.getItem(STORAGE_KEYS.tour)).toBeNull();
    } finally {
      setItem.mockRestore();
    }
  });
});

describe('a narrow window gets Classic view (§14 F6)', () => {
  const notice = /The 3D office needs a window at least 768 pixels wide, so this is Classic view/;

  it('sends the office to its Classic twin, never starting the world', async () => {
    media.wide = false;
    const { router } = renderRoute('/?agent=memory&as_of=2026-09-18');

    await waitFor(() => expect(router.state.location.pathname).toBe('/classic/agents/memory'));
    expect(router.state.location.search).toBe('?as_of=2026-09-18');
    expect(await screen.findByText(notice)).toHaveAttribute('role', 'status');
    expect(stub.rendered).toBe(false);
  });

  it('offers Classic only in the view switch', async () => {
    media.wide = false;
    renderRoute('/classic');

    const views = await screen.findByRole('navigation', { name: 'View' });
    expect(within(views).queryByRole('link', { name: /Office/ })).not.toBeInTheDocument();
    expect(within(views).getByText('Office')).toHaveAttribute('aria-disabled', 'true');
    expect(within(views).getByText('(needs a wider window)')).toHaveClass('sr-only');
    expect(within(views).getByRole('link', { name: 'Classic' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('leaves the office when the window narrows, and offers it again when it widens', async () => {
    const { router } = renderRoute('/');
    await screen.findByTestId('world');
    expect(screen.queryByText(notice)).not.toBeInTheDocument();

    narrowTo(false);
    await waitFor(() => expect(router.state.location.pathname).toBe('/classic'));
    expect(await screen.findByText(notice)).toBeInTheDocument();

    narrowTo(true);
    expect(screen.queryByText(notice)).not.toBeInTheDocument();
    expect(
      within(screen.getByRole('navigation', { name: 'View' })).getByRole('link', {
        name: 'Office',
      }),
    ).toBeInTheDocument();
  });

  it('keeps the WebGL notice alone when both apply', async () => {
    media.wide = false;
    useSession.getState().failWebgl();
    renderRoute('/classic');

    expect(await screen.findByText(COPY.webglFallback)).toBeInTheDocument();
    expect(screen.queryByText(notice)).not.toBeInTheDocument();
  });
});

describe('the pixel art (F6)', () => {
  function art(name: string) {
    return document.querySelector(`svg[data-art="${name}"]`);
  }

  it('puts an empty tray over an inbox with no assessment', async () => {
    server.use(
      http.get('*/api/v1/risk/assessments', () =>
        HttpResponse.json({ items: [], total: 0, limit: 500, offset: 0 }),
      ),
    );
    renderRoute('/classic/inbox');

    expect(await screen.findByText(COPY.inboxNoAssessment)).toBeInTheDocument();
    expect(art('tray')).toHaveAttribute('aria-hidden', 'true');
  });

  it('pins an empty corkboard over an empty decision chain', async () => {
    renderRoute(`/classic/briefs/${briefId()}`);

    expect(await screen.findByText(COPY.emptyDecisionChain)).toBeInTheDocument();
    expect(art('corkboard')).toBeInTheDocument();
  });

  it('shows an empty cabinet when MEMORY holds no records', async () => {
    server.use(
      http.get('*/api/v1/entities/:type', () =>
        HttpResponse.json({ items: [], total: 0, limit: 1, offset: 0 }),
      ),
    );
    renderRoute('/classic/agents/memory');

    expect(await screen.findByText(COPY.memoryNoRecords)).toBeInTheDocument();
    expect(art('cabinet')).toBeInTheDocument();
  });

  it('draws an agent on the page that is not there, and a desk for a brief that is not', async () => {
    const first = renderRoute('/classic/nowhere');
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
    expect(art('agent')).toBeInTheDocument();
    first.unmount();

    server.use(http.get('*/api/v1/risk/briefs/:id', () => refuse(404, 'BRIEF_NOT_FOUND')));
    renderRoute('/classic/briefs/no-such-brief');
    expect(await screen.findByText('No brief exists at this address.')).toBeInTheDocument();
    expect(art('desk')).toBeInTheDocument();
  });

  it('shows an agent at a desk while the office loads', () => {
    render(<LoadingArt label="the 3D office" caption="Setting up the office" />);

    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(within(status).getByText('Loading the 3D office…')).toHaveClass('sr-only');
    expect(within(status).getByText('Setting up the office')).toHaveAttribute(
      'aria-hidden',
      'true',
    );
    expect(art('agent')).toBeInTheDocument();
    expect(art('desk')).toBeInTheDocument();
  });
});
