import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { z } from 'zod';

import {
  ApiError,
  ContractError,
  GET_RETRIES,
  NetworkError,
  REQUEST_ID_HEADER,
  TIMEOUTS,
  backoffMs,
  getJson,
  isApiFailure,
  postJson,
} from '@/api/client';

const shape = z.strictObject({ value: z.number().int() });

function reply(status: number, body: unknown, requestId: string | null = 'rid-1'): Response {
  const headers = new Headers({ 'Content-Type': 'application/json' });
  if (requestId !== null) headers.set(REQUEST_ID_HEADER, requestId);
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), { status, headers });
}

function envelope(code: string, details: unknown = null, requestId = 'rid-body') {
  return { error: { code, message: `message for ${code}`, details, request_id: requestId } };
}

/** A fetch that never settles until its signal aborts, like the platform's own. */
function hangingFetch() {
  return vi.fn(
    (_input: URL, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        const abort = () => reject(new DOMException('aborted', 'AbortError'));
        if (init.signal?.aborted) abort();
        init.signal?.addEventListener('abort', abort);
      }),
  );
}

let fetchMock: Mock<(input: URL, init: RequestInit) => Promise<Response>>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('a successful GET', () => {
  it('asks for JSON on the page origin and returns the parsed body with its request id', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { value: 7 }));

    const result = await getJson('/api/v1/thing', shape);

    expect(result.data).toEqual({ value: 7 });
    expect(result.status).toBe(200);
    expect(result.requestId).toBe('rid-1');
    expect(result.call).toMatchObject({
      method: 'GET',
      path: '/api/v1/thing',
      status: 200,
      requestId: 'rid-1',
    });
    expect(result.call.durationMs).toBeGreaterThanOrEqual(0);
    const [url, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(url.toString()).toBe(`${window.location.origin}/api/v1/thing`);
    expect(init.method).toBe('GET');
    expect(init.headers).toEqual({ Accept: 'application/json' });
    expect(init.body).toBeNull();
  });

  it('records a missing request id as null', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { value: 1 }, null));

    const result = await getJson('/api/v1/thing', shape);

    expect(result.requestId).toBeNull();
  });

  it('parses an accepted non-2xx status as a success body', async () => {
    fetchMock.mockResolvedValueOnce(reply(503, { value: 0 }));

    const result = await getJson('/api/v1/thing', shape, { acceptStatuses: [503] });

    expect(result.status).toBe(503);
    expect(result.data).toEqual({ value: 0 });
  });
});

describe('a POST', () => {
  it('sends its JSON body once and is never retried', async () => {
    fetchMock.mockRejectedValue(new TypeError('failed to fetch'));

    await expect(postJson('/api/v1/write', { a: 1 }, shape)).rejects.toBeInstanceOf(NetworkError);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(init.method).toBe('POST');
    expect(init.body).toBe('{"a":1}');
    expect(init.headers).toEqual({
      Accept: 'application/json',
      'Content-Type': 'application/json',
    });
  });

  it('is not retried on a 5xx either', async () => {
    fetchMock.mockResolvedValue(reply(500, envelope('INTERNAL_ERROR')));

    await expect(postJson('/api/v1/write', {}, shape)).rejects.toBeInstanceOf(ApiError);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('returns a 201 body with its status', async () => {
    fetchMock.mockResolvedValueOnce(reply(201, { value: 2 }));

    const result = await postJson('/api/v1/write', {}, shape);

    expect(result.status).toBe(201);
    expect(result.call.method).toBe('POST');
  });
});

describe('contract failures', () => {
  it('rejects a success body that is not JSON', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, 'not json'));

    const error = await getJson('/api/v1/thing', shape).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ContractError);
    expect((error as ContractError).message).toBe('The response was not JSON.');
    expect((error as ContractError).requestId).toBe('rid-1');
  });

  it('rejects a body that does not match its schema, naming every issue', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { value: 1.5, extra: true }));

    const error = (await getJson('/api/v1/thing', shape).catch(
      (caught: unknown) => caught,
    )) as ContractError;

    expect(error).toBeInstanceOf(ContractError);
    expect(error.issues.some((issue) => issue.startsWith('value:'))).toBe(true);
    expect(error.issues.some((issue) => issue.startsWith('(root):'))).toBe(true);
  });

  it('rejects a 4xx without the error envelope, without retrying', async () => {
    fetchMock.mockResolvedValue(reply(418, { detail: 'teapot' }));

    const error = await getJson('/api/v1/thing', shape).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ContractError);
    expect((error as ContractError).message).toBe("HTTP 418 arrived without the API's error body.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('API errors', () => {
  it('maps the envelope, preferring the header request id', async () => {
    fetchMock.mockResolvedValueOnce(reply(404, envelope('BRIEF_NOT_FOUND')));

    const error = (await getJson('/api/v1/thing', shape).catch(
      (caught: unknown) => caught,
    )) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.code).toBe('BRIEF_NOT_FOUND');
    expect(error.message).toBe('message for BRIEF_NOT_FOUND');
    expect(error.requestId).toBe('rid-1');
    expect(error.details).toBeNull();
    expect(error.reason).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('falls back to the body request id when the header is missing', async () => {
    fetchMock.mockResolvedValueOnce(reply(409, envelope('DECISION_CONFLICT'), null));

    const error = (await getJson('/api/v1/thing', shape).catch(
      (caught: unknown) => caught,
    )) as ApiError;

    expect(error.requestId).toBe('rid-body');
  });

  it.each([
    [{ reason: 'PREDECESSOR_NOT_HEAD' }, 'PREDECESSOR_NOT_HEAD'],
    [{ reason: 7 }, null],
    [{ other: 'x' }, null],
    [[{ loc: ['body'], message: 'bad', type: 'x' }], null],
  ])('reads details.reason from %j as %j', async (details, reason) => {
    fetchMock.mockResolvedValueOnce(reply(409, envelope('DECISION_CONFLICT', details)));

    const error = (await getJson('/api/v1/thing', shape).catch(
      (caught: unknown) => caught,
    )) as ApiError;

    expect(error.reason).toBe(reason);
  });
});

describe('GET retries', () => {
  it('retries a 5xx API error twice with backoff, then fails', async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(() => Promise.resolve(reply(500, envelope('INTERNAL_ERROR'))));

    const pending = getJson('/api/v1/thing', shape).catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(backoffMs(0));
    await vi.advanceTimersByTimeAsync(backoffMs(1));
    const error = await pending;

    expect(error).toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1 + GET_RETRIES);
  });

  it('retries a network failure and returns the later success', async () => {
    vi.useFakeTimers();
    fetchMock
      .mockRejectedValueOnce(new TypeError('failed to fetch'))
      .mockResolvedValueOnce(reply(200, { value: 3 }));

    const pending = getJson('/api/v1/thing', shape);
    await vi.advanceTimersByTimeAsync(backoffMs(0));

    await expect(pending).resolves.toMatchObject({ data: { value: 3 } });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('treats a 5xx without the envelope as an unreachable API and retries it', async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(() => Promise.resolve(reply(502, '<html>bad gateway</html>')));

    const pending = getJson('/api/v1/thing', shape).catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(backoffMs(0) + backoffMs(1));
    const error = (await pending) as NetworkError;

    expect(error).toBeInstanceOf(NetworkError);
    expect(error.message).toBe('The API could not be reached (HTTP 502).');
    expect(error.timedOut).toBe(false);
    expect(error.requestId).toBe('rid-1');
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('never retries a 4xx API error', async () => {
    fetchMock.mockResolvedValue(reply(422, envelope('INVALID_REQUEST', [])));

    await expect(getJson('/api/v1/thing', shape)).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('waits 300 ms, then 900 ms', () => {
    expect([backoffMs(0), backoffMs(1)]).toEqual([300, 900]);
  });
});

describe('timeouts and cancellation', () => {
  it('times a GET out after 15 s as a network error that states it timed out', async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(hangingFetch());

    const pending = getJson('/api/v1/thing', shape, { timeoutMs: 1_000 }).catch(
      (caught: unknown) => caught,
    );
    await vi.advanceTimersByTimeAsync(1_000 + backoffMs(0) + 1_000 + backoffMs(1) + 1_000);
    const error = (await pending) as NetworkError;

    expect(error).toBeInstanceOf(NetworkError);
    expect(error.timedOut).toBe(true);
    expect(error.message).toBe('The request timed out.');
    expect(error.requestId).toBeNull();
    expect(TIMEOUTS.get).toBe(15_000);
  });

  it('uses the default GET timeout when none is given', async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(hangingFetch());
    const controller = new AbortController();

    const pending = getJson('/api/v1/thing', shape, { signal: controller.signal }).catch(
      (caught: unknown) => caught,
    );
    await vi.advanceTimersByTimeAsync(TIMEOUTS.get - 1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    await vi.advanceTimersByTimeAsync(backoffMs(0));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    controller.abort();
    await pending;
  });

  it('uses the default POST timeout when none is given', async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(hangingFetch());

    const pending = postJson('/api/v1/write', {}, shape).catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(TIMEOUTS.post - 1);
    let settled = false;
    void pending.then(() => (settled = true));
    await Promise.resolve();
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);

    expect(await pending).toMatchObject({ timedOut: true });
  });

  it('passes a caller cancellation through without retrying', async () => {
    fetchMock.mockImplementation(hangingFetch());
    const controller = new AbortController();

    const pending = getJson('/api/v1/thing', shape, { signal: controller.signal }).catch(
      (caught: unknown) => caught,
    );
    controller.abort();
    const error = await pending;

    expect(error).toBeInstanceOf(DOMException);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('rejects at once for a signal that is already aborted', async () => {
    fetchMock.mockImplementation(hangingFetch());
    const controller = new AbortController();
    controller.abort();

    const error = await getJson('/api/v1/thing', shape, { signal: controller.signal }).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(DOMException);
    expect(isApiFailure(error)).toBe(false);
  });

  it('does not retry a failure once the caller has cancelled', async () => {
    const controller = new AbortController();
    fetchMock.mockImplementation(() => {
      controller.abort();
      return Promise.resolve(reply(500, envelope('INTERNAL_ERROR')));
    });

    const error = await getJson('/api/v1/thing', shape, { signal: controller.signal }).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('isApiFailure', () => {
  it('recognises the three failure classes and nothing else', () => {
    const call = {
      method: 'GET' as const,
      path: '/x',
      status: null,
      durationMs: 0,
      requestId: null,
    };
    expect(isApiFailure(new NetworkError('n', false, call))).toBe(true);
    expect(isApiFailure(new ContractError('c', [], call))).toBe(true);
    expect(
      isApiFailure(
        new ApiError(500, { code: 'X', message: 'm', details: null, request_id: 'r' }, 'r', call),
      ),
    ).toBe(true);
    expect(isApiFailure(new Error('plain'))).toBe(false);
  });
});
