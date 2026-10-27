/**
 * The dashboard's calls to the backend. Same origin, so the browser sends the session
 * cookie by itself; every change also sends the header the server demands of requests
 * that are really the dashboard's own.
 */
import type { Item, Scholar } from './logic';

export type Me = { email: string; name: string | null };

/** A failed call, with the server's reason when it gave one (`not_waiting`, ...). */
export class AdminError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
  ) {
    super(code);
  }
}

async function failure(response: Response): Promise<AdminError> {
  try {
    const detail = (await response.json())?.detail;
    if (typeof detail === 'string') return new AdminError(detail, response.status);
  } catch {
    // not JSON -- a proxy's error page, say
  }
  return new AdminError(`http_${response.status}`, response.status);
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new AdminError('network', 0);
  }
  if (!response.ok) throw await failure(response);
  return (await response.json()) as T;
}

const CHANGE = { 'Content-Type': 'application/json', 'X-Requested-With': 'maqati3' };

function post<T>(path: string, body?: unknown): Promise<T> {
  return call<T>(path, {
    method: 'POST',
    headers: CHANGE,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const fetchMe = () => call<Me>('/api/v1/admin/me');
export const fetchItems = () => call<Item[]>('/api/v1/admin/submissions');
export const fetchScholars = () =>
  call<(Scholar & { entry_count: number })[]>('/api/v1/scholars');

export const registerItem = (sha256: string, scholarId: string) =>
  post<{ entry_id: string }>(`/api/v1/admin/submissions/${encodeURIComponent(sha256)}/register`, {
    scholar_id: scholarId,
  });

export const discardItem = (sha256: string) =>
  post<{ status: string }>(`/api/v1/admin/submissions/${encodeURIComponent(sha256)}/discard`);

export const addScholar = (scholar: Scholar) => post<Scholar>('/api/v1/admin/scholars', scholar);

export const signOut = () => post<{ status: string }>('/api/v1/admin/auth/logout');

/** The player's source: the cookie authorises it, since a <video> cannot send headers. */
export function mediaUrl(sha256: string): string {
  return `/api/v1/admin/submissions/${encodeURIComponent(sha256)}/media`;
}
