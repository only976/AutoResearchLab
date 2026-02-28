import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

const REWRITES: Array<{ from: string; to: string }> = [
  { from: "/api/plan", to: "/api/maars/plan" },
  { from: "/api/plans", to: "/api/maars/plans" },
  { from: "/api/execution", to: "/api/maars/execution" },
  { from: "/api/settings", to: "/api/maars/settings" },
  { from: "/api/db/clear", to: "/api/maars/db/clear" }
]

function rewritePath(pathname: string): string | null {
  for (const item of REWRITES) {
    if (pathname === item.from) return item.to
    if (pathname.startsWith(item.from + "/")) {
      return pathname.replace(item.from, item.to)
    }
  }
  return null
}

export function middleware(request: NextRequest) {
  const rewritten = rewritePath(request.nextUrl.pathname)
  if (!rewritten) return NextResponse.next()
  const url = request.nextUrl.clone()
  url.pathname = rewritten
  return NextResponse.rewrite(url)
}

export const config = {
  matcher: [
    "/api/plan/:path*",
    "/api/plans",
    "/api/execution/:path*",
    "/api/settings",
    "/api/db/clear"
  ]
}
