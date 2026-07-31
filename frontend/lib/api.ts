"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8100/api";

export async function apiFetch<T>(path: string, options: RequestInit = {}, token?: string | null): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const body = await response.text();
    let message = body;
    try {
      const parsed = JSON.parse(body) as { detail?: string | { message?: string } };
      message = typeof parsed.detail === "string" ? parsed.detail : parsed.detail?.message ?? body;
    } catch {
      // Keep a plain-text response as-is.
    }
    throw new Error(message || "请求失败，请稍后重试");
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/**
 * 同 apiFetch，但当后端返回 404 时返回 null（用于"该资源可能尚不存在"的场景，
 * 例如章节尚未生成 Beat 卡、蓝图尚未初始化）。其它错误仍抛出。
 */
export async function apiFetchOptional<T>(path: string, options: RequestInit = {}, token?: string | null): Promise<T | null> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
    cache: "no-store",
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const body = await response.text();
    let message = body;
    try {
      const parsed = JSON.parse(body) as { detail?: string | { message?: string } };
      message = typeof parsed.detail === "string" ? parsed.detail : parsed.detail?.message ?? body;
    } catch {
      // Keep a plain-text response as-is.
    }
    throw new Error(message || "请求失败，请稍后重试");
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
