import { API_BASE_URL } from "@/lib/api"

export async function GET() {
  const upstream = await fetch(`${API_BASE_URL}/health`, { method: "GET" })
  const payload = await upstream.text()
  return new Response(payload, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json"
    }
  })
}
