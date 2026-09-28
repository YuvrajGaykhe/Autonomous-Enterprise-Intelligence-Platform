import { QueryClient } from '@tanstack/react-query';

/** Retries belong to the API client (§6.2); the query layer never adds its own. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false, staleTime: 10_000 },
      mutations: { retry: false },
    },
  });
}
