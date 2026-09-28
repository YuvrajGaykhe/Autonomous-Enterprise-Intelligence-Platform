import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { COPY } from '@/copy';

import { recorded } from '../support/fixtures';
import { renderRoute } from '../support/render';
import { server } from '../support/server';

const health = recorded('health.json', 'GET', '/api/v1/health').body as Record<string, unknown>;

describe('the HUD', () => {
  it('shows the product name and the recorded health from GET /api/v1/health', async () => {
    renderRoute('/classic');

    expect(screen.getByRole('link', { name: COPY.productName })).toBeInTheDocument();
    const light = await screen.findByTestId('health-light');
    expect(light).toHaveTextContent('API healthy');
    expect(light).toHaveTextContent('database ok · v0.1.0');
  });

  it('shows the checking state while the health request is in flight', () => {
    server.use(http.get('*/api/v1/health', () => new Promise(() => undefined)));
    renderRoute('/classic');

    expect(screen.getByText('API: checking…')).toBeInTheDocument();
  });

  it('reads a 503 as an unhealthy API with its database unavailable', async () => {
    server.use(
      http.get('*/api/v1/health', () =>
        HttpResponse.json(
          { ...health, status: 'unhealthy', checks: { database: 'unavailable' } },
          { status: 503, headers: { 'X-Request-ID': 'r503' } },
        ),
      ),
    );
    renderRoute('/classic');

    const light = await screen.findByTestId('health-light');
    expect(light).toHaveTextContent('API unhealthy');
    expect(light).toHaveTextContent('database unavailable');
  });

  it('shows an unreachable API with its code and offers Retry', async () => {
    let calls = 0;
    server.use(
      http.get('*/api/v1/health', () => {
        calls += 1;
        return HttpResponse.json(
          { error: { code: 'NOT_FOUND', message: 'Not Found', details: null, request_id: 'r404' } },
          { status: 404, headers: { 'X-Request-ID': 'r404' } },
        );
      }),
    );
    renderRoute('/classic');

    const header = screen.getByRole('banner');
    expect(await within(header).findByText('API unreachable')).toBeInTheDocument();
    expect(within(header).getByText('NOT_FOUND · request r404')).toBeInTheDocument();
    const before = calls;
    await userEvent.click(within(header).getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(calls).toBeGreaterThan(before));
  });

  it('says so when no request id arrived with the failure', async () => {
    server.use(http.get('*/api/v1/health', () => HttpResponse.text('nope', { status: 418 })));
    renderRoute('/classic');

    const header = screen.getByRole('banner');
    expect(await within(header).findByText('CONTRACT_ERROR · request none')).toBeInTheDocument();
  });
});

describe('the as_of selector (D-F-14)', () => {
  it('defaults to the explicit date 2026-09-18', () => {
    renderRoute('/classic');

    expect(screen.getByLabelText('as_of')).toHaveValue('date');
    expect(screen.getByLabelText('as_of date')).toHaveValue('2026-09-18');
  });

  it('keeps the choice in the URL, and Auto hides the date', async () => {
    const { router } = renderRoute('/classic');

    await userEvent.selectOptions(screen.getByLabelText('as_of'), 'auto');
    expect(router.state.location.search).toBe('?as_of=auto');
    expect(screen.queryByLabelText('as_of date')).not.toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('as_of'), 'date');
    expect(router.state.location.search).toBe('?as_of=2026-09-18');
  });

  it('reads a date from the URL and takes a new real date only', async () => {
    const { router } = renderRoute('/classic?as_of=2026-09-01');
    const input = screen.getByLabelText('as_of date');
    expect(input).toHaveValue('2026-09-01');

    // A date picker reports one complete value per change; an empty value is ignored.
    fireEvent.change(input, { target: { value: '' } });
    expect(router.state.location.search).toBe('?as_of=2026-09-01');
    fireEvent.change(input, { target: { value: '2026-09-10' } });
    expect(router.state.location.search).toBe('?as_of=2026-09-10');
    await screen.findByTestId('health-light');
  });
});

describe('the routes', () => {
  it('opens Classic view at / until the office exists, keeping the query', async () => {
    const { router } = renderRoute('/?as_of=auto');

    await waitFor(() => expect(router.state.location.pathname).toBe('/classic'));
    expect(router.state.location.search).toBe('?as_of=auto');
  });

  it('shows the system status on the Classic overview, with its request id', async () => {
    renderRoute('/classic');

    const card = screen.getByRole('region', { name: 'System status' });
    expect(await within(card).findByText('ai-ceo-layer1')).toBeInTheDocument();
    expect(within(card).getByText('0.1.0')).toBeInTheDocument();
    expect(within(card).getByText(/^fixture\d+$/)).toBeInTheDocument();
  });

  it('says when no request id arrived with the system status', async () => {
    server.use(http.get('*/api/v1/health', () => HttpResponse.json(health)));
    renderRoute('/classic');

    const card = screen.getByRole('region', { name: 'System status' });
    expect(await within(card).findByText('none received')).toBeInTheDocument();
  });

  it('shows the not-found page for an unknown address, with a way back', async () => {
    renderRoute('/nowhere?as_of=auto');

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Classic view' })).toHaveAttribute(
      'href',
      '/classic?as_of=auto',
    );
    await screen.findByTestId('health-light');
  });

  it('offers a skip link to the main content', async () => {
    renderRoute('/classic');

    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
    await screen.findByTestId('health-light');
  });
});
