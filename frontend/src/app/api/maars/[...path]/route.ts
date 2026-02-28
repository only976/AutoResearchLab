import { API_BASE_URL } from "@/lib/api"

async function proxy(request: Request, path: string) {
  const url = new URL(request.url)
  const upstream = `${API_BASE_URL}/api/maars/${path}${url.search}`
  const headers: HeadersInit = { "Content-Type": request.headers.get("content-type") || "application/json" }
  const init: RequestInit = {
    method: request.method,
    headers
  }

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text()
  }

  const res = await fetch(upstream, init)
  const payload = await res.text()
  return new Response(payload, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("content-type") || "application/json"
    }
  })
}

export async function GET(request: Request, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path.join("/"))
}

export async function POST(request: Request, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path.join("/"))
}

export async function PUT(request: Request, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path.join("/"))
}

export async function PATCH(request: Request, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path.join("/"))
}

export async function DELETE(request: Request, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path.join("/"))
}
