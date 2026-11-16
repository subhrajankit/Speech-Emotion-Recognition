/**
 * VoiceSense AI — HTTP/API Error Classification
 * Pure helpers for distinguishing authentication failures (401/403) from
 * ordinary HTTP and network errors, so callers can trigger re-auth flows
 * without misclassifying 404s or connectivity problems.
 */

export type AuthFailureKind = 'unauthenticated' | 'forbidden';

export class AuthError extends Error {
  readonly status: number;
  readonly kind: AuthFailureKind;

  constructor(message: string, status: number, kind: AuthFailureKind) {
    super(message);
    this.name = 'AuthError';
    this.status = status;
    this.kind = kind;
  }
}

export function isAuthError(err: unknown): err is AuthError {
  return err instanceof AuthError;
}

/**
 * Builds the appropriate error for a non-OK response.
 * - 401 -> AuthError('unauthenticated')
 * - 403 -> AuthError('forbidden')
 * - anything else -> plain Error preserving the existing detail/fallback text
 */
export function createHttpError(
  status: number,
  detail: unknown,
  fallbackMessage: string
): Error {
  const message =
    typeof detail === 'string' && detail.trim()
      ? detail.trim()
      : fallbackMessage;

  if (status === 401) {
    return new AuthError(message, status, 'unauthenticated');
  }
  if (status === 403) {
    return new AuthError(message, status, 'forbidden');
  }
  return new Error(message);
}
