/**
 * Unified API proxy - forwards /api/* to backend.
 * - /api/health → backend /health
 * - /api/* → backend /api/{path}  (includes maars, ideas, experiments, config, etc.)
 */
import { API_BASE_URL } from "@/lib/api"

function buildBackendUrl(path: string[], search: string): string {
  const base = path.length === 1 && path[0] === "health" ? "" : `/api/${path.join("/")}`
  return `${API_BASE_URL}${base || "/health"}${search}`
}

async function proxy(
  request: Request,
  path: string[]
): Promise<Response> {
  const url = new URL(request.url)
  const backendUrl = buildBackendUrl(path, url.search)
  const headers: HeadersInit = {
    "Content-Type": request.headers.get("content-type") || "application/json",
  }

  const init: RequestInit = { method: request.method, headers }
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text()
  }

  const res = await fetch(backendUrl, init)
  const contentType = res.headers.get("content-type") || "application/json"
  const isSSE = contentType.includes("text/event-stream")
  const isBinary = contentType.includes("octet-stream") || contentType.startsWith("image/")

  if (isSSE && res.body) {
    return new Response(res.body, {
      status: res.status,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
      },
    })
  }

  const payload = isBinary ? await res.arrayBuffer() : await res.text()
  return new Response(payload, {
    status: res.status,
    headers: { "Content-Type": contentType },
  })
}

type RouteContext = { params: { path: string[] } }

export async function GET(request: Request, context: RouteContext) {
  return proxy(request, context.params.path)
}

export async function POST(request: Request, context: RouteContext) {
  return proxy(request, context.params.path)
}

export async function PUT(request: Request, context: RouteContext) {
  return proxy(request, context.params.path)
}

export async function PATCH(request: Request, context: RouteContext) {
  return proxy(request, context.params.path)
}

export async function DELETE(request: Request, context: RouteContext) {
  return proxy(request, context.params.path)
}
