import type { SessionCreateRequest, SessionInfo } from "./types";

const apiBase = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "")
  ?? "http://127.0.0.1:8008";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getApiBase(): string {
  return apiBase;
}

export function listSessions(): Promise<SessionInfo[]> {
  return request<SessionInfo[]>("/sessions");
}

export function createSession(payload: SessionCreateRequest): Promise<SessionInfo> {
  return request<SessionInfo>("/sessions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function connectSession(sessionId: string): Promise<void> {
  return request(`/sessions/${sessionId}/connect`, {
    method: "POST",
  }).then(() => undefined);
}

export function disconnectSession(sessionId: string): Promise<void> {
  return request(`/sessions/${sessionId}/disconnect`, {
    method: "POST",
  }).then(() => undefined);
}