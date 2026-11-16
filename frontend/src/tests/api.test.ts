import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  fetchHistorySessions,
  fetchSessionDetail,
  deleteSession,
  purgeAllHistory,
} from '../services/api';
import { AuthError, isAuthError, createHttpError } from '../lib/httpErrors';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('createHttpError classification', () => {
  it('maps 401 to an unauthenticated AuthError', () => {
    const err = createHttpError(401, 'Invalid or expired authentication token: Token has expired', 'fallback');
    expect(isAuthError(err)).toBe(true);
    expect((err as AuthError).kind).toBe('unauthenticated');
    expect((err as AuthError).status).toBe(401);
    expect(err.message).toContain('expired');
  });

  it('maps 403 to a forbidden AuthError', () => {
    const err = createHttpError(403, 'User account is inactive', 'fallback');
    expect(isAuthError(err)).toBe(true);
    expect((err as AuthError).kind).toBe('forbidden');
    expect((err as AuthError).status).toBe(403);
  });

  it('leaves 404 as a plain not-found Error', () => {
    const err = createHttpError(404, "Session 'sess_1' not found.", 'fallback');
    expect(isAuthError(err)).toBe(false);
    expect(err).toBeInstanceOf(Error);
    expect(err.message).toBe("Session 'sess_1' not found.");
  });

  it('leaves other statuses as plain Errors with fallback semantics', () => {
    const err = createHttpError(500, undefined, 'Failed to fetch sessions (500)');
    expect(isAuthError(err)).toBe(false);
    expect(err.message).toBe('Failed to fetch sessions (500)');
  });
});

describe('Protected history API functions — consistent auth classification', () => {
  const TOKEN = 'test-token';

  it('fetchHistorySessions: 401 → AuthError, 403 → AuthError, 404 → plain Error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, { detail: 'expired' })));
    await expect(fetchHistorySessions(TOKEN)).rejects.toSatisfy(isAuthError);

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(403, { detail: 'inactive' })));
    const forbidden = await fetchHistorySessions(TOKEN).catch((e) => e);
    expect(isAuthError(forbidden)).toBe(true);
    expect(forbidden.kind).toBe('forbidden');

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(404, { detail: 'not found' })));
    const notFound = await fetchHistorySessions(TOKEN).catch((e) => e);
    expect(isAuthError(notFound)).toBe(false);
    expect(notFound.message).toBe('not found');
  });

  it('fetchSessionDetail: 401 → AuthError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, { detail: 'missing token' })));
    const err = await fetchSessionDetail('sess_1', TOKEN).catch((e) => e);
    expect(isAuthError(err)).toBe(true);
    expect(err.kind).toBe('unauthenticated');
  });

  it('deleteSession: 403 → AuthError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(403, { detail: 'forbidden' })));
    const err = await deleteSession('sess_1', TOKEN).catch((e) => e);
    expect(isAuthError(err)).toBe(true);
    expect(err.kind).toBe('forbidden');
  });

  it('purgeAllHistory: network rejection is NOT an auth failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const err = await purgeAllHistory(TOKEN).catch((e) => e);
    expect(isAuthError(err)).toBe(false);
    expect(err).toBeInstanceOf(TypeError);
  });

  it('purgeAllHistory: 500 keeps existing plain-Error semantics', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(500, { detail: 'db down' })));
    const err = await purgeAllHistory(TOKEN).catch((e) => e);
    expect(isAuthError(err)).toBe(false);
    expect(err.message).toBe('db down');
  });

  it('sends Bearer token and returns parsed JSON on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, [{ id: 'sess_1' }]));
    vi.stubGlobal('fetch', fetchMock);

    const data = await fetchHistorySessions(TOKEN);
    expect(data).toEqual([{ id: 'sess_1' }]);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe(`Bearer ${TOKEN}`);
  });
});
