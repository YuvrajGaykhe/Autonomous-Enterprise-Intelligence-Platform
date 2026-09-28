/**
 * MSW, answering from the recorded fixtures only (spec §12.1). A request no fixture recorded
 * fails the test (`onUnhandledRequest: 'error'`).
 */

import { http, HttpResponse, type RequestHandler } from 'msw';
import { setupServer } from 'msw/node';

import { EXCHANGE_FILES, loadExchanges } from './fixtures';

function pathnameOf(path: string): string {
  return path.split('?')[0] ?? path;
}

/** One handler per recorded GET pathname: the first recording of that pathname answers. */
export function fixtureHandlers(): RequestHandler[] {
  const seen = new Set<string>();
  const handlers: RequestHandler[] = [];
  let counter = 0;
  for (const file of EXCHANGE_FILES) {
    for (const exchange of loadExchanges(file)) {
      const pathname = pathnameOf(exchange.path);
      if (exchange.method !== 'GET' || seen.has(pathname)) continue;
      seen.add(pathname);
      counter += 1;
      const requestId = `fixture${counter}`;
      handlers.push(
        http.get(`*${pathname}`, () =>
          HttpResponse.json(exchange.body as Record<string, unknown>, {
            status: exchange.status,
            headers: { 'X-Request-ID': requestId },
          }),
        ),
      );
    }
  }
  return handlers;
}

export const server = setupServer(...fixtureHandlers());
