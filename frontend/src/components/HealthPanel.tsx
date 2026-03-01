"use client"

import { useCallback, useEffect, useState } from "react"
import { api } from "@/lib/api"

type HealthDetail = {
  backend?: { ok?: boolean }
  docker?: { ok?: boolean; message?: string }
}

type ConfigResponse = {
  llm_model?: string
  llm_api_base?: string | null
  llm_api_key_configured?: boolean
}

export default function HealthPanel() {
  const [health, setHealth] = useState<HealthDetail | null>(null)
  const [config, setConfig] = useState<ConfigResponse | null>(null)

  const loadHealth = useCallback(async () => {
    try {
      const data = await api<HealthDetail>("health/detail")
      setHealth(data)
    } catch {
      setHealth(null)
    }
  }, [])

  const loadConfig = useCallback(async () => {
    try {
      const data = await api<ConfigResponse>("config")
      setConfig(data)
    } catch {
      setConfig(null)
    }
  }, [])

  useEffect(() => {
    loadHealth()
    loadConfig()
  }, [loadHealth, loadConfig])

  const backendOk = health?.backend?.ok
  const dockerOk = health?.docker?.ok

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-md border border-border bg-card p-4 text-xs text-foreground">
          <div className="text-muted-foreground">Backend</div>
          <div className="mt-2 text-sm font-medium">{backendOk ? "运行中" : "异常"}</div>
        </div>
        <div className="rounded-md border border-border bg-card p-4 text-xs text-foreground">
          <div className="text-muted-foreground">Docker</div>
          <div className="mt-2 text-sm font-medium">{dockerOk ? "运行中" : "未启动"}</div>
          <div className="mt-2 text-xs text-muted-foreground">{health?.docker?.message || ""}</div>
        </div>
        <div className="rounded-md border border-border bg-card p-4 text-xs text-foreground">
          <div className="text-muted-foreground">LLM</div>
          <div className="mt-2 text-sm font-medium">{config?.llm_model || "Unknown"}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {config?.llm_api_key_configured ? "API Key 已配置" : "API Key 未配置"}
          </div>
        </div>
      </div>
      {!dockerOk ? (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
          Docker 未启动，实验执行会失败。请启动 Docker Desktop 或运行 colima start。
        </div>
      ) : null}
    </div>
  )
}
