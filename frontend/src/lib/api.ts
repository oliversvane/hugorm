"use client";
import { getSupabase } from "./supabase";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const supabase = getSupabase();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) return {};
  return { Authorization: `Bearer ${session.access_token}` };
}

export async function apiGet<T>(path: string): Promise<T> {
  const headers = await authHeader();
  const resp = await fetch(`${BASE}${path}`, { headers });
  if (!resp.ok) throw new ApiError(resp.status, await resp.text());
  return resp.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {
    ...(await authHeader()),
    "Content-Type": "application/json",
  };
  const resp = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) throw new ApiError(resp.status, await resp.text());
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export async function apiDelete(path: string): Promise<void> {
  const headers = await authHeader();
  const resp = await fetch(`${BASE}${path}`, { method: "DELETE", headers });
  if (!resp.ok && resp.status !== 204)
    throw new ApiError(resp.status, await resp.text());
}

export async function apiUpload<T>(
  path: string,
  file: File,
): Promise<T> {
  const headers = await authHeader();
  const fd = new FormData();
  fd.append("file", file);
  const resp = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers,
    body: fd,
  });
  if (!resp.ok) throw new ApiError(resp.status, await resp.text());
  return resp.json() as Promise<T>;
}

export function apiBaseUrl(): string {
  return BASE;
}
