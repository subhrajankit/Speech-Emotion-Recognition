/**
 * VoiceSense AI — REST API Service
 * Interacts with FastAPI backend endpoints for health, auth, and history.
 */

import { getApiUrl } from '../lib/env';
import { createHttpError } from '../lib/httpErrors';
import { HealthResponse } from '../types/speech';
import {
  SessionSummary,
  SessionDetail,
  DeleteHistoryResponse,
} from '../types/history';

export interface UserResponse {
  id: string;
  username: string;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  user_id: string;
  username: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const url = `${getApiUrl()}/api/health`;
  const response = await fetch(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }

  return response.json();
}

export function extractApiErrorMessage(errorData: any, status: number, fallback: string): string {
  if (!errorData) return `${fallback} (${status})`;
  if (typeof errorData.detail === 'string' && errorData.detail.trim()) {
    return errorData.detail.trim();
  }
  if (Array.isArray(errorData.detail)) {
    const messages = errorData.detail
      .map((item: any) => {
        if (typeof item === 'string') return item;
        if (item && item.msg) {
          const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : '';
          return field ? `${field}: ${item.msg}` : item.msg;
        }
        return JSON.stringify(item);
      })
      .filter(Boolean);
    if (messages.length > 0) return messages.join('; ');
  }
  if (typeof errorData.message === 'string' && errorData.message.trim()) {
    return errorData.message.trim();
  }
  return `${fallback} (${status})`;
}

/**
 * Register a new user account.
 * Endpoint: POST /api/auth/register
 */
export async function registerUser(username: string, password: string): Promise<UserResponse> {
  const url = `${getApiUrl()}/api/auth/register`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(extractApiErrorMessage(errorData, response.status, 'Registration failed'));
  }

  return response.json();
}

/**
 * Authenticate username and password, issuing an HS256 JWT access token.
 * Endpoint: POST /api/auth/login
 */
export async function loginUser(username: string, password: string): Promise<TokenResponse> {
  const url = `${getApiUrl()}/api/auth/login`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(extractApiErrorMessage(errorData, response.status, 'Login failed'));
  }

  return response.json();
}

/**
 * Retrieve current user profile.
 * Endpoint: GET /api/auth/me
 */
export async function getMe(token: string): Promise<UserResponse> {
  const url = `${getApiUrl()}/api/auth/me`;
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw createHttpError(response.status, errorData.detail, `Failed to fetch profile (${response.status})`);
  }

  return response.json();
}

/**
 * List all sessions belonging to the authenticated user.
 * Endpoint: GET /api/history/sessions
 */
export async function fetchHistorySessions(token: string): Promise<SessionSummary[]> {
  const url = `${getApiUrl()}/api/history/sessions`;
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw createHttpError(response.status, errorData.detail, `Failed to fetch sessions (${response.status})`);
  }

  return response.json();
}

/**
 * Retrieve session details (predictions, transcripts, messages).
 * Endpoint: GET /api/history/sessions/{id}
 */
export async function fetchSessionDetail(sessionId: string, token: string): Promise<SessionDetail> {
  const url = `${getApiUrl()}/api/history/sessions/${encodeURIComponent(sessionId)}`;
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw createHttpError(response.status, errorData.detail, `Failed to fetch session detail (${response.status})`);
  }

  return response.json();
}

/**
 * Delete a specific session.
 * Endpoint: DELETE /api/history/sessions/{id}
 */
export async function deleteSession(
  sessionId: string,
  token: string
): Promise<{ deleted: boolean; session_id: string }> {
  const url = `${getApiUrl()}/api/history/sessions/${encodeURIComponent(sessionId)}`;
  const response = await fetch(url, {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw createHttpError(response.status, errorData.detail, `Failed to delete session (${response.status})`);
  }

  return response.json();
}

/**
 * Delete-My-Data: Purge ALL sessions and transcripts for the authenticated user.
 * Endpoint: DELETE /api/history
 */
export async function purgeAllHistory(token: string): Promise<DeleteHistoryResponse> {
  const url = `${getApiUrl()}/api/history`;
  const response = await fetch(url, {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw createHttpError(response.status, errorData.detail, `Failed to purge history (${response.status})`);
  }

  return response.json();
}
