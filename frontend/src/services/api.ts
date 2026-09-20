/**
 * VoiceSense AI — REST API Service
 */

import { getApiUrl } from '../lib/env';
import { HealthResponse } from '../types/speech';
import { HistoryItem } from '../types/history';

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

export async function fetchAuthToken(clientId = 'vite-client'): Promise<string> {
  const url = `${getApiUrl()}/api/auth/token`;
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId }),
    });

    if (response.ok) {
      const data = await response.json();
      return data.token || '';
    }
  } catch (err) {
    console.warn('[API] Failed to fetch auth token:', err);
  }
  return '';
}

/**
 * Clean architectural seam for Phase 9 (/api/history).
 * In Phase 3, this returns null/empty if the backend endpoint is not yet mounted.
 */
export async function fetchRemoteHistory(_limit = 50): Promise<HistoryItem[] | null> {
  const url = `${getApiUrl()}/api/history`;
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    if (response.ok) {
      return await response.json();
    }
  } catch {
    // Expected in Phase 3 prior to Phase 9 endpoint
  }
  return null;
}
