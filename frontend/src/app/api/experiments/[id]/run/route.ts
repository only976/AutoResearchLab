import { API_BASE_URL } from "@/lib/api"

export async function POST(request: Request, context: { params: { id: string } }) {
  const body = await request.text()
  const upstream = await fetch(`${API_BASE_URL}/api/experiments/${context.params.id}/run`, {
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
