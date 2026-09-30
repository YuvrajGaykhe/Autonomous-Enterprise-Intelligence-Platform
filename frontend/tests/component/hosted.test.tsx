/**
 * The hosted demo (spec §14 F5, §16): the mock sources cannot be reached there, so their panels
 * keep the real failed health check and add Appendix A's caption. Nothing else changes.
 */

import { screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { COPY } from '@/copy';

import { renderRoute } from '../support/render';

const hosting = vi.hoisted(() => ({ hosted: true }));
vi.mock('@/lib/hosting', () => ({
  get HOSTED() {
    return hosting.hosted;
  },
}));

afterEach(() => {
  hosting.hosted = true;
});

async function healthOf(id: string) {
  const view = renderRoute(`/classic/agents/${id}`);
  await screen.findByRole('heading', { level: 1 });
  const health = screen.getByRole('region', { name: 'Health check' });
  await within(health).findByText(/^(healthy|unhealthy)$/);
  return { view, health };
}

describe('a mock source on the hosted site (§16)', () => {
  it('shows the real health check and says the source runs in local mode only', async () => {
    for (const id of ['odoo_mock', 'rest_mock']) {
      const { view, health } = await healthOf(id);
      expect(within(health).getByText('unhealthy')).toBeInTheDocument();
      expect(within(health).getByText(COPY.mockSourceHostedOnly)).toBeInTheDocument();
      view.unmount();
    }
  });

  it('adds nothing for the CSV source, which the hosted API reads from its own bundle', async () => {
    const { health } = await healthOf('csv_demo');
    expect(within(health).getByText('healthy')).toBeInTheDocument();
    expect(within(health).queryByText(COPY.mockSourceHostedOnly)).toBeNull();
  });

  it('adds nothing to a local build', async () => {
    hosting.hosted = false;
    const { health } = await healthOf('odoo_mock');
    expect(within(health).queryByText(COPY.mockSourceHostedOnly)).toBeNull();
  });
});
