/**
 * The one HTTP client the app uses (spec §6.1, §6.2, §7.6, R-F-7).
 *
 * - Every request goes to a relative path under `/api/v1/` on the page's own origin.
 * - Every response's `X-Request-ID` is carried on the result or on the error.
 * - A non-2xx body in the API's error envelope becomes an `ApiError`. A network failure, a
 *   timeout, or a 5xx without that envelope (a proxy or gateway answering for an unreachable
 *   API) becomes a `NetworkError`. Any other unexpected body becomes a `ContractError`.
 * - Every success body is parsed with its Zod schema before use; partially valid data is
 *   never returned.
 * - A GET is retried at most twice, with backoff, on a `NetworkError` or a 5xx `ApiError`,
 *   and never on a 4xx. A POST is never retried: its outcome may be unknown, and the caller
 *   re-reads before it offers a retry.
 */

import { z } from 'zod';

export const REQUEST_ID_HEADER = 'X-Request-ID';

/** Timeouts in milliseconds (§6.2, PROPOSED values). */
export const TIMEOUTS = { get: 15_000, assessment: 60_000, post: 30_000 } as const;
export const GET_RETRIES = 2;

/** The delay before GET retry `attempt` (0-based): 300 ms, then 900 ms. */
export function backoffMs(attempt: number): number {
  return 300 * 3 ** attempt;
}

type Method = 'GET' | 'POST';

/** What "Show the API call" reports for one request (§8.3). */
export interface ApiCall {
  method: Method;
  path: string;
  status: number | null;
  durationMs: number;
  requestId: string | null;
}

export interface ApiResult<T> {
  data: T;
  status: number;
  requestId: string | null;
  call: ApiCall;
}

const errorEnvelope = z.strictObject({
  error: z.strictObject({
    code: z.string(),
    message: z.string(),
    details: z
      .union([z.array(z.record(z.string(), z.unknown())), z.record(z.string(), z.unknown())])
      .nullable(),
    request_id: z.string(),
  }),
});

export type ErrorDetails = z.infer<typeof errorEnvelope>['error']['details'];

/** The API answered with its structured error envelope. */
export class ApiError extends Error {
  override name = 'ApiError';
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetails;
  readonly requestId: string;
  readonly call: ApiCall;

  constructor(
    status: number,
    body: z.infer<typeof errorEnvelope>['error'],
    requestId: string,
    call: ApiCall,
  ) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.details = body.details;
    this.requestId = requestId;
    this.call = call;
  }

  /** `details.reason`, when the API stated one (the 409 families of §7.6). */
  get reason(): string | null {
    const details = this.details;
    if (details === null || Array.isArray(details)) return null;
    return typeof details.reason === 'string' ? details.reason : null;
  }
}

/** The request never produced an API answer: no network, a timeout, or an unreachable API. */
export class NetworkError extends Error {
  override name = 'NetworkError';
  readonly timedOut: boolean;
  readonly call: ApiCall;

  constructor(message: string, timedOut: boolean, call: ApiCall) {
    super(message);
    this.timedOut = timedOut;
    this.call = call;
  }

  get requestId(): string | null {
    return this.call.requestId;
  }
}

/** The API answered, but not with the shape this frontend was built against. */
export class ContractError extends Error {
  override name = 'ContractError';
  readonly issues: readonly string[];
  readonly call: ApiCall;

  constructor(message: string, issues: readonly string[], call: ApiCall) {
    super(message);
    this.issues = issues;
    this.call = call;
  }

  get requestId(): string | null {
    return this.call.requestId;
  }
}

export type ApiFailure = ApiError | NetworkError | ContractError;

export function isApiFailure(error: unknown): error is ApiFailure {
  return (
    error instanceof ApiError || error instanceof NetworkError || error instanceof ContractError
  );
}

/** Zod issues as `path: message` lines, for the error state's details. */
export function describeIssues(error: z.ZodError): string[] {
  return error.issues.map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`);
}

export interface RequestOptions {
  signal?: AbortSignal | undefined;
  timeoutMs?: number;
  /** Non-2xx statuses whose body is a success body, e.g. 503 from `/health`. */
  acceptStatuses?: readonly number[];
}

const NOT_JSON = Symbol('not JSON');

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return NOT_JSON;
  }
}

async function send<S extends z.ZodType>(
  method: Method,
  path: string,
  schema: S,
  body: unknown,
  options: RequestOptions,
): Promise<ApiResult<z.infer<S>>> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(
    () => {
      timedOut = true;
      controller.abort();
    },
    options.timeoutMs ?? (method === 'GET' ? TIMEOUTS.get : TIMEOUTS.post),
  );
  const cancel = () => controller.abort(options.signal?.reason);
  options.signal?.addEventListener('abort', cancel);
  if (options.signal?.aborted) cancel();

  const started = performance.now();
  const call: ApiCall = { method, path, status: null, durationMs: 0, requestId: null };
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (method === 'POST') headers['Content-Type'] = 'application/json';

  let response: Response;
  let text: string;
  try {
    response = await fetch(new URL(path, window.location.origin), {
      method,
      headers,
      body: method === 'POST' ? JSON.stringify(body) : null,
      signal: controller.signal,
    });
    call.status = response.status;
    call.requestId = response.headers.get(REQUEST_ID_HEADER);
    text = await response.text();
  } catch (error) {
    call.durationMs = performance.now() - started;
    if (options.signal?.aborted) throw error;
    throw new NetworkError(
      timedOut ? 'The request timed out.' : 'The API could not be reached.',
      timedOut,
      call,
    );
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', cancel);
  }
  call.durationMs = performance.now() - started;

  const json = parseJson(text);
  const status = response.status;
  if (response.ok || (options.acceptStatuses ?? []).includes(status)) {
    if (json === NOT_JSON) throw new ContractError('The response was not JSON.', [], call);
    const parsed = schema.safeParse(json);
    if (!parsed.success) {
      throw new ContractError(
        'The response did not match the shape this frontend expects.',
        describeIssues(parsed.error),
        call,
      );
    }
    return { data: parsed.data, status, requestId: call.requestId, call };
  }
  const envelope = errorEnvelope.safeParse(json);
  if (envelope.success) {
    throw new ApiError(
      status,
      envelope.data.error,
      call.requestId ?? envelope.data.error.request_id,
      call,
    );
  }
  if (status >= 500) {
    throw new NetworkError(`The API could not be reached (HTTP ${status}).`, false, call);
  }
  throw new ContractError(`HTTP ${status} arrived without the API's error body.`, [], call);
}

function retryable(error: unknown): boolean {
  return error instanceof NetworkError || (error instanceof ApiError && error.status >= 500);
}

/** GET a JSON body, retrying at most twice on a network failure or a 5xx. */
export async function getJson<S extends z.ZodType>(
  path: string,
  schema: S,
  options: RequestOptions = {},
): Promise<ApiResult<z.infer<S>>> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await send('GET', path, schema, undefined, options);
    } catch (error) {
      if (attempt >= GET_RETRIES || !retryable(error) || options.signal?.aborted) throw error;
      await new Promise((resolve) => setTimeout(resolve, backoffMs(attempt)));
    }
  }
}

/** POST a JSON body once. Never retried automatically (R-F-7). */
export async function postJson<S extends z.ZodType>(
  path: string,
  body: unknown,
  schema: S,
  options: RequestOptions = {},
): Promise<ApiResult<z.infer<S>>> {
  return await send('POST', path, schema, body, options);
}
