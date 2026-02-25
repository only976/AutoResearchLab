import { API_BASE_URL } from "@/lib/api"

export async function GET(request: Request, context: { params: { id: string; name: string } }) {
  const url = new URL(request.url)
  const upstream = await fetch(
    `${API_BASE_URL}/api/experiments/${context.params.id}/artifacts/${context.params.name}${url.search}`,
    { method: "GET" }
  )
  const payload = await upstream.arrayBuffer()
  return new Response(payload, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/octet-stream"
    }
  })
}
