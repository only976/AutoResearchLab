/**
 * Unified API client - all requests go through Next.js /api proxy.
 * API_BASE_URL is for server-side proxy routes only.
 */

export const API_BASE_URL = process.env.API_BASE_URL || "http://localhost:8888"

function buildPath(path: string): string {
  const p = path.replace(/^\//, "")
  return p.startsWith("api/") ? `/${p}` : `/api/${p}`
}

/** Raw fetch - returns Response for cases needing res.ok, headers, etc. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(buildPath(path), init)
}

type ApiInit = Omit<RequestInit, "body"> & { body?: unknown }

/** JSON API - throws on !res.ok, returns parsed JSON. */
export async function api<T>(path: string, init?: ApiInit): Promise<T> {
  const url = buildPath(path)
  const { body: rawBody, ...rest } = init || {}
  const headers: HeadersInit = { ...(rest.headers as Record<string, string>) }
  let body: BodyInit | null | undefined
  if (rawBody !== undefined && typeof rawBody === "object" && !(rawBody instanceof Blob) && !(rawBody instanceof FormData)) {
    body = JSON.stringify(rawBody)
    if (!(headers as Record<string, string>)["Content-Type"]) (headers as Record<string, string>)["Content-Type"] = "application/json"
  } else {
    body = rawBody as BodyInit | null | undefined
  }
  const res = await fetch(url, { ...rest, headers, body })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}
