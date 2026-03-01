"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Server, Key, Database, RefreshCw, ShieldCheck, ShieldAlert, Save, Monitor } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { PageHeader } from "@/components/PageHeader"
import { MaarsSettingsSection } from "@/components/MaarsSettingsSection"
import { api } from "@/lib/api"

type Config = {
  llm_model?: string
  llm_api_base?: string
  llm_api_key?: string
  frontend_port?: number | string
}

export default function ConfigPage() {
  const [config, setConfig] = useState<Config | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const loadConfig = async () => {
    setLoading(true)
    try {
      const data = await api<Partial<Config>>("config")
      setConfig({
        llm_model: String(data.llm_model ?? ""),
        llm_api_base: String(data.llm_api_base ?? ""),
        llm_api_key: String(data.llm_api_key ?? ""),
        frontend_port: Number(data.frontend_port) || 3030,
      })
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  const saveConfig = async () => {
    if (!config) return
    setSaving(true)
    setError(null)
    setSaved(false)
    const payload = {
      ...config,
      frontend_port: Number(config.frontend_port) || 3030,
    }
    try {
      await api("config", { method: "POST", body: payload })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    loadConfig()
  }, [])

  const updateField = (key: keyof Config, value: string | number) => {
    setConfig((prev) => (prev ? { ...prev, [key]: value } : null))
  }

  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.1 },
    },
  }

  const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 },
  }

  return (
    <div className="flex flex-col h-full">
      <PageHeader
        title="Configuration"
        description="System config stored in config.json."
      >
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadConfig} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button onClick={saveConfig} disabled={saving || !config}>
            <Save className={`mr-2 h-4 w-4 ${saving ? "animate-pulse" : ""}`} />
            {saving ? "Saving..." : saved ? "Saved" : "Save"}
          </Button>
        </div>
      </PageHeader>

      <div className="flex-1 space-y-6">
        {error && (
          <div className="bg-destructive/10 border border-destructive/20 text-destructive p-4 rounded-lg">
            {error}
          </div>
        )}

        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid gap-6 md:grid-cols-2 lg:grid-cols-3"
        >
          <motion.div variants={item}>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">LLM Model</CardTitle>
                <Database className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <Input
                  value={config?.llm_model ?? ""}
                  onChange={(e) => updateField("llm_model", e.target.value)}
                  placeholder="e.g. gemini-3-flash-preview"
                  className="font-mono"
                />
                <p className="text-xs text-muted-foreground mt-2">
                  Active language model
                </p>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={item}>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">API Base URL</CardTitle>
                <Server className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <Input
                  value={config?.llm_api_base ?? ""}
                  onChange={(e) => updateField("llm_api_base", e.target.value)}
                  placeholder="Leave empty for native (e.g. Gemini)"
                  className="font-mono"
                />
                <p className="text-xs text-muted-foreground mt-2">
                  LLM service endpoint
                </p>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={item}>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">API Key</CardTitle>
                <Key className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <Input
                    type="password"
                    value={config?.llm_api_key ?? ""}
                    onChange={(e) => updateField("llm_api_key", e.target.value)}
                    placeholder="API key"
                    className="font-mono flex-1"
                  />
                  {(config?.llm_api_key ?? "").trim() ? (
                    <ShieldCheck className="h-5 w-5 text-green-500 shrink-0" />
                  ) : (
                    <ShieldAlert className="h-5 w-5 text-amber-500 shrink-0" />
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  Authentication
                </p>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={item}>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Frontend Port</CardTitle>
                <Monitor className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <Input
                  type="number"
                  value={String(config?.frontend_port ?? 3030)}
                  onChange={(e) => updateField("frontend_port", e.target.value)}
                  placeholder="3030"
                  className="font-mono"
                />
                <p className="text-xs text-muted-foreground mt-2">
                  前端开发服务器端口
                </p>
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>

        <div className="mt-12 pt-8 border-t">
          <MaarsSettingsSection />
        </div>
      </div>
    </div>
  )
}
