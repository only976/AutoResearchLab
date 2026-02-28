import { API_BASE_URL } from "@/lib/api"

export async function GET(request: Request) {
  const url = new URL(request.url)
  const upstream = await fetch(`${API_BASE_URL}/api/maars/events${url.search}`, {
    headers: { Accept: "text/event-stream" }
  })

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive"
    }
  })
}
