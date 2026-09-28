/**
 * MSW, answering from the recorded fixtures only (spec §12.1). A request no fixture recorded
 * fails the test (`onUnhandledRequest: 'error'`).
 *
 * A GET is answered by the recording of its exact path and query when there is one, else by the
 * first recording of its path. `decision-flow.json` is recorded after writes, so its answers
 * describe a later database state; tests opt into them with `server.use`.
 */

import { http, HttpResponse, type RequestHandler } from 'msw';
import { setupServer } from 'msw/node';

import { EXCHANGE_FILES, loadExchanges, type RecordedExchange } from './fixtures';

/** Fixture files whose answers are not the database's starting state. */
export const LATER_STATE_FILES = ['decision-flow.json'];

function pathnameOf(path: string): string {
  return path.split('?')[0] ?? path;
}

/** A recorded answer as MSW returns it, with a request id of its own. */
export function answer(exchange: RecordedExchange, requestId: string) {
  return HttpResponse.json(exchange.body as Record<string, unknown>, {
    status: exchange.status,
    headers: { 'X-Request-ID': requestId },
  });
}

/** One handler per recorded GET path. */
export function fixtureHandlers(): RequestHandler[] {
  const byPathname = new Map<string, RecordedExchange[]>();
  for (const file of EXCHANGE_FILES.filter((name) => !LATER_STATE_FILES.includes(name))) {
    for (const exchange of loadExchanges(file)) {
      if (exchange.method !== 'GET') continue;
      const pathname = pathnameOf(exchange.path);
      byPathname.set(pathname, [...(byPathname.get(pathname) ?? []), exchange]);
    }
  }
  let counter = 0;
  return [...byPathname].map(([pathname, exchanges]) => {
    counter += 1;
    const requestId = `fixture${counter}`;
    return http.get(`*${pathname}`, ({ request }) => {
      const url = new URL(request.url);
      const exact = exchanges.find((item) => item.path === `${url.pathname}${url.search}`);
      return answer(exact ?? (exchanges[0] as RecordedExchange), requestId);
    });
  });
}

export const server = setupServer(...fixtureHandlers());
