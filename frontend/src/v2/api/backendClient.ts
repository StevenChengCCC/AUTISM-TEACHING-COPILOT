export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api";

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string; message?: string };
      detail = payload.detail ?? payload.message ?? detail;
    } catch {
      // Keep the HTTP fallback when the server did not return JSON.
    }
    throw new Error(`Lesson Kit API request failed: ${detail}`);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const backendClient = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T,>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  del: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
};
