import { API_BASE_URL } from "@/lib/api"

export async function GET() {
  const upstream = await fetch(`${API_BASE_URL}/api/experiments`, { method: "GET" })
  const payload = await upstream.text()
  return new Response(payload, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json"
    }
  })
}

export async function POST(request: Request) {
  const body = await request.text()
  const upstream = await fetch(`${API_BASE_URL}/api/experiments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body
  })
  const payload = await upstream.text()
  return new Response(payload, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json"
    }
  })
}
