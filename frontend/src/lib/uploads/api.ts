/**
 * The upload page's calls to the backend. Same origin: in development Next rewrites
 * /api to the backend (next.config.ts), in production Caddy routes it there directly.
 */
import type { CheckOut, DecisionBody } from './batch';

export type ScholarItem = { id: string; name_ar: string; name_en: string; entry_count: number };

export type TopicItem = {
  id: string;
  name_ar: string;
  name_en: string;
  children: TopicItem[];
};

/** A failed call, with the server's reason when it gave one (`no_readable_audio`, ...). */
export class UploadError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
  ) {
    super(code);
  }
}

function errorFrom(status: number, body: string): UploadError {
  try {
    const detail = JSON.parse(body)?.detail;
    if (typeof detail === 'string') return new UploadError(detail, status);
  } catch {
    // not JSON -- a proxy's error page, say
  }
  return new UploadError(status === 0 ? 'network' : `http_${status}`, status);
}

/**
 * Upload one file and get back what it is. XMLHttpRequest rather than fetch, because
 * only XHR reports upload progress -- and a contributor sending twenty videos over a
 * phone connection needs to see that something is happening.
 */
export function uploadFile(
  file: File,
  key: string,
  onProgress: (fraction: number) => void,
): Promise<CheckOut> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/v1/uploads');
    xhr.setRequestHeader('X-Upload-Key', key);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      if (xhr.status === 200) resolve(JSON.parse(xhr.responseText) as CheckOut);
      else reject(errorFrom(xhr.status, xhr.responseText));
    };
    xhr.onerror = () => reject(new UploadError('network', 0));
    const form = new FormData();
    form.append('file', file, file.name);
    xhr.send(form);
  });
}

export async function sendDecision(sha256: string, body: DecisionBody, key: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api/v1/uploads/${encodeURIComponent(sha256)}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Upload-Key': key },
      body: JSON.stringify(body),
    });
  } catch {
    throw new UploadError('network', 0);
  }
  if (!response.ok) throw errorFrom(response.status, await response.text());
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw errorFrom(response.status, await response.text());
  return (await response.json()) as T;
}

export const fetchScholars = () => getJson<ScholarItem[]>('/api/v1/scholars');
export const fetchTopics = () => getJson<TopicItem[]>('/api/v1/topics');

/** Where a pending upload can be played for comparison. A <video src> cannot send a
 * header, so this one URL carries the key as ?k=. */
export function mediaUrl(previewId: string, key: string): string {
  return `/api/v1/uploads/${encodeURIComponent(previewId)}/media?k=${encodeURIComponent(key)}`;
}
