import { QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router';

import { createQueryClient } from '@/app/queryClient';
import { routes } from '@/app/routes';

/** Render the real route table at `path`, with a fresh query cache. */
export function renderRoute(path = '/classic') {
  const client = createQueryClient();
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const view = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...view, router, client };
}
