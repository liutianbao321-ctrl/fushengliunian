"use client";

import { apiUrl } from "@/lib/api";

export function projectStreamRequest(projectId: string, token: string, lastEventId: string, signal: AbortSignal) {
  return fetch(apiUrl(`/projects/${projectId}/stream?last_event_id=${encodeURIComponent(lastEventId)}`), {
    headers: { Authorization: `Bearer ${token}`, "Last-Event-ID": lastEventId },
    signal,
  });
}
