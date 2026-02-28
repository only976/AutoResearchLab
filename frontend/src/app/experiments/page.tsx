"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

export default function ExperimentsRedirectPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace("/experiments/maars")
  }, [router])

  return (
    <div className="rounded-2xl border border-slate-800 bg-panel px-6 py-8">
      <div className="text-sm text-slate-400">Redirecting</div>
      <div className="mt-2 text-lg font-semibold text-white">Opening MAARS Lab...</div>
      <div className="mt-2 text-sm text-slate-400">
        If you are not redirected, open the MAARS Lab from the sidebar.
      </div>
    </div>
  )
}
