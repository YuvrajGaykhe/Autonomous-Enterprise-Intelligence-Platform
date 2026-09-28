/**
 * Test-side API helpers: recorded answers served by MSW, the bodies a page sent, and a few
 * answers that only a failure can produce (a hung request, a dropped connection).
 */

import { delay, http, HttpResponse } from 'msw';

import { answer } from './server';
import {
  decisionFlow,
  recordedAssessmentList,
  recordedBriefs,
  type RecordedExchange,
} from './fixtures';

export { answer };

/** A request that never settles, for loading states. */
export const hang = () => delay('infinite') as Promise<never>;

/** A dropped connection, which the client reads as a network failure. */
export const drop = () => HttpResponse.error();

/** The API's error envelope with a status. */
export function refuse(
  status: number,
  code: string,
  details: unknown = null,
  requestId = 'rid-refused',
) {
  return HttpResponse.json(
    { error: { code, message: `message for ${code}`, details, request_id: requestId } },
    { status, headers: { 'X-Request-ID': requestId } },
  );
}

/** The recorded brief responses, CUST-007 first. */
export function briefBodies() {
  return recordedBriefs().map(
    (exchange) =>
      exchange.body as {
        id: string;
        payload_hash: string;
        assessment_id: string;
        payload: Record<string, unknown>;
      } & Record<string, unknown>,
  );
}

export function briefId(index = 0): string {
  return briefBodies()[index]?.id ?? '';
}

export interface ListItem {
  id: string;
  brief_ids: string[];
  executive_worthy: boolean;
  customer_source_id: string | null;
  layer1_fingerprint: string;
}

export function listBody() {
  return recordedAssessmentList<{
    items: ListItem[];
    total: number;
    limit: number;
    offset: number;
  }>();
}

/** The recorded decision-flow exchange that matches. */
export function flowExchange(predicate: (item: RecordedExchange) => boolean): RecordedExchange {
  const found = decisionFlow().find(predicate);
  if (found === undefined) throw new Error('no such exchange in decision-flow.json');
  return found;
}

/** A recorded refusal by its reason or code. */
export function recordedRefusal(reason: string): RecordedExchange {
  return flowExchange((item) => {
    const error = (item.body as { error?: { code: string; details: { reason?: string } | null } })
      .error;
    return error !== undefined && (error.details?.reason === reason || error.code === reason);
  });
}

export const recordedApproval = () =>
  flowExchange((item) => item.method === 'POST' && item.status === 201);
export const recordedRejection = () =>
  decisionFlow().filter(
    (item) => item.method === 'POST' && item.status === 201,
  )[1] as RecordedExchange;
export const recordedChain = () =>
  flowExchange(
    (item) => item.method === 'GET' && item.path.endsWith('/decisions') && item.status === 200,
  );

/** Serve a brief's chain from a list the test controls. */
export function chainHandler(items: () => unknown[]) {
  return http.get('*/api/v1/risk/briefs/:id/decisions', () =>
    HttpResponse.json({ items: items() }, { headers: { 'X-Request-ID': 'rid-chain' } }),
  );
}
