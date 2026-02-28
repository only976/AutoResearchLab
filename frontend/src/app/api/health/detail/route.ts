import { NextResponse } from "next/server"
import { API_BASE_URL } from "@/lib/api"

export async function GET(request: Request) {
  const url = new URL(request.url)
  try {
    const upstream = await fetch(`${API_BASE_URL}/api/health/detail${url.search}`, { method: "GET" })
    const payload = await upstream.text()
    return new Response(payload, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") || "application/json"
      }
    })
  } catch (err) {
    return NextResponse.json(
      { backend: { ok: false }, docker: { ok: false, message: "Backend unreachable" } },
      { status: 200 }
    )
  }
}
