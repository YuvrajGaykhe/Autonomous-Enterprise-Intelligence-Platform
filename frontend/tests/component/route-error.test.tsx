import { render, screen } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

import { RouteError } from '@/app/RouteError';

function Broken(): never {
  throw new Error('render failure');
}

describe('a route that throws while rendering', () => {
  it('shows the error state instead of a blank page', () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const router = createMemoryRouter(
      [{ path: '/', element: <Broken />, errorElement: <RouteError /> }],
      { initialEntries: ['/'] },
    );
    render(<RouterProvider router={router} />);

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('This page failed unexpectedly.');
    expect(alert).toHaveTextContent('UNEXPECTED');
    quiet.mockRestore();
  });
});
