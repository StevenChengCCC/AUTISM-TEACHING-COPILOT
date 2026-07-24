import { clearSession, getBearerToken, refreshSession } from "../auth/authSession";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api";

export function resolveBackendAssetUrl(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  if (value.startsWith("data:") || /^https?:\/\//.test(value)) return value;
  const backendOrigin = new URL(API_BASE, window.location.origin).origin;
  return `${backendOrigin}${value.startsWith("/") ? value : `/${value}`}`;
}

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

export class LessonKitApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public retryable: boolean,
    public requestId?: string,
    public fieldErrors?: { field: string; message: string; code?: string }[],
  ) { super(message); }
}

async function request<T>(path: string, options: RequestOptions = {}, hasRetried = false): Promise<T> {
  const token = await getBearerToken();
  const requestId = crypto.randomUUID();
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "X-Request-ID": requestId,
      ...options.headers,
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (response.status === 401 && !hasRetried && token) {
    const refreshed = await refreshSession();
    if (refreshed) return request<T>(path, options, true);
    clearSession();
    window.dispatchEvent(new Event("lessonkit:session-expired"));
  }
  if (response.status === 401 && (hasRetried || !token)) {
    clearSession();
    window.dispatchEvent(new Event("lessonkit:session-expired"));
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    let code = `http_${response.status}`;
    let retryable = response.status >= 500;
    let responseRequestId = response.headers.get("X-Request-ID") ?? requestId;
    let fieldErrors: { field: string; message: string; code?: string }[] | undefined;
    try {
      const payload = (await response.json()) as { detail?: string; message?: string;code?:string;retryable?:boolean;requestId?:string;fieldErrors?:typeof fieldErrors };
      detail = payload.detail ?? payload.message ?? detail;
      code = payload.code ?? code;
      retryable = payload.retryable ?? retryable;
      responseRequestId = payload.requestId ?? responseRequestId;
      fieldErrors = payload.fieldErrors;
    } catch {
      // Keep the HTTP fallback when the server did not return JSON.
    }
    throw new LessonKitApiError(detail,response.status,code,retryable,responseRequestId,fieldErrors);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const backendClient = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T,>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  del: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
  putFile: (
    url: string,
    file: File,
    headers: Record<string, string>,
    onProgress?: (percent: number) => void,
  ): Promise<void> =>
    new Promise((resolve, reject) => {
      const upload = new XMLHttpRequest();
      upload.open("PUT", url);
      Object.entries(headers).forEach(([name, value]) => upload.setRequestHeader(name, value));
      upload.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100));
      };
      upload.onload = () => {
        if (upload.status >= 200 && upload.status < 300) {
          onProgress?.(100);
          resolve();
          return;
        }
        reject(new Error(`Private upload failed with HTTP ${upload.status}.`));
      };
      upload.onerror = () => reject(new Error("Private upload failed. Check the network and retry."));
      upload.onabort = () => reject(new Error("Private upload was cancelled."));
      upload.send(file);
    }),
};
