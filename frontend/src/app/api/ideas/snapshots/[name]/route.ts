import { API_BASE_URL } from "@/lib/api"

export async function GET(request: Request, context: { params: { name: string } }) {
  const url = new URL(request.url)
  const safeName = encodeURIComponent(context.params.name)
  const upstream = await fetch(`${API_BASE_URL}/api/ideas/snapshots/${safeName}${url.search}`, {
    method: "GET"
  })
  const payload = await upstream.text()
  return new Response(payload, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json"
    }
  })
}
