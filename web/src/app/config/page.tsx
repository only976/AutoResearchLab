"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Server, Key, Database, RefreshCw, ShieldCheck, ShieldAlert } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { Badge } from "@/components/ui/Badge"
import { PageHeader } from "@/components/PageHeader"

type ConfigResponse = {
  llm_model?: string
  llm_api_base?: string | null
  llm_api_key_configured?: boolean
  workspace_dir?: string
}

export default function ConfigPage() {
  const [config, setConfig] = useState<ConfigResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadConfig = async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/config")
      if (!res.ok) throw new Error("Failed to fetch configuration")
      const data = await res.json()
      setConfig(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadConfig()
  }, [])

  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  }

  const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 }
  }

  return (
    <div className="flex flex-col h-full">
      <PageHeader 
        title="Configuration" 
        description="System settings and environment status."
      >
        <Button variant="outline" onClick={loadConfig} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
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
                <div className="text-2xl font-bold">{config?.llm_model || "Unknown"}</div>
                <p className="text-xs text-muted-foreground">
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
                <div className="text-2xl font-bold truncate" title={config?.llm_api_base || "Default"}>
                  {config?.llm_api_base || "Default"}
                </div>
                <p className="text-xs text-muted-foreground">
                  LLM service endpoint
                </p>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div variants={item}>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">API Key Status</CardTitle>
                <Key className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <div className="text-2xl font-bold">
                    {config?.llm_api_key_configured ? "Configured" : "Missing"}
                  </div>
                  {config?.llm_api_key_configured ? (
                    <ShieldCheck className="h-5 w-5 text-green-500" />
                  ) : (
                    <ShieldAlert className="h-5 w-5 text-red-500" />
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Authentication status
                </p>
              </CardContent>
            </Card>
          </motion.div>
        </motion.div>

        <motion.div variants={item} initial="hidden" animate="show" transition={{ delay: 0.3 }}>
          <Card>
            <CardHeader>
              <CardTitle>Environment Variables</CardTitle>
              <CardDescription>
                Read-only view of critical system environment variables.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="grid grid-cols-[1fr_2fr] gap-4 items-center border-b pb-4">
                  <div className="font-medium text-sm text-muted-foreground">Workspace Directory</div>
                  <div className="font-mono text-sm break-all">{config?.workspace_dir || "N/A"}</div>
                </div>
                {/* Add more detailed config items here if the API provides them */}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  )
}
