"use client"

import { useCallback, useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Search, RefreshCw, Terminal, AlertCircle } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card"
import { Input } from "@/components/ui/Input"
import { Button } from "@/components/ui/Button"
import { Badge } from "@/components/ui/Badge"
import { cn } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"

type ExperimentItem = {
  id: string
  title: string
  status: string
  updated_at?: number
}

type LogsResponse = {
  lines: string[]
}

export default function LogsPage() {
  const [experiments, setExperiments] = useState<ExperimentItem[]>([])
  const [filteredExperiments, setFilteredExperiments] = useState<ExperimentItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [lines, setLines] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [logsLoading, setLogsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState("")

  const loadExperiments = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/experiments")
      if (!res.ok) throw new Error("Failed to fetch experiments")
      const data = await res.json()
      setExperiments(data)
      setFilteredExperiments(data)
      
      // Auto-select first if none selected
      if (!selectedId && data.length > 0) {
        setSelectedId(data[0].id)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  useEffect(() => {
    loadExperiments()
  }, [loadExperiments])

  useEffect(() => {
    const filtered = experiments.filter(exp => 
      exp.title?.toLowerCase().includes(searchTerm.toLowerCase()) || 
      exp.id.toLowerCase().includes(searchTerm.toLowerCase())
    )
    setFilteredExperiments(filtered)
  }, [searchTerm, experiments])

  const loadLogs = async (expId: string) => {
    if (!expId) return
    setLogsLoading(true)
    try {
      const res = await fetch(`/api/experiments/${expId}/logs?lines=1000`)
      if (!res.ok) throw new Error("Failed to fetch logs")
      const data: LogsResponse = await res.json()
      setLines(data.lines || [])
    } catch (err) {
      console.error(err)
      setLines(["Error loading logs."])
    } finally {
      setLogsLoading(false)
    }
  }

  useEffect(() => {
    if (selectedId) {
      loadLogs(selectedId)
      
      // Poll for logs every 5 seconds if the experiment is likely active
      const interval = setInterval(() => {
         // We could check status here, but for now just simple polling
         loadLogs(selectedId)
      }, 5000)
      
      return () => clearInterval(interval)
    }
  }, [selectedId])

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case "completed": return "bg-green-500/10 text-green-500 border-green-500/20"
      case "running": return "bg-blue-500/10 text-blue-500 border-blue-500/20"
      case "failed": return "bg-red-500/10 text-red-500 border-red-500/20"
      default: return "bg-slate-500/10 text-slate-500 border-slate-500/20"
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)]">
      <PageHeader 
        title="System Logs" 
        description="Inspect experiment execution logs."
        className="mb-4 pb-4"
      >
        <Button size="sm" variant="outline" onClick={loadExperiments} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
        </Button>
      </PageHeader>

      <div className="flex flex-1 gap-6 overflow-hidden">
        {/* Sidebar List */}
        <div className="w-80 flex flex-col gap-4 flex-shrink-0">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input 
              placeholder="Filter logs..." 
              className="pl-9" 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div className="flex-1 overflow-y-auto space-y-2 pr-2">
            {loading && experiments.length === 0 ? (
               <div className="text-center py-8 text-muted-foreground">Loading...</div>
            ) : filteredExperiments.length === 0 ? (
               <div className="text-center py-8 text-muted-foreground">No experiments found.</div>
            ) : (
              filteredExperiments.map(item => (
                <div
                  key={item.id}
                  onClick={() => setSelectedId(item.id)}
                  className={cn(
                    "cursor-pointer rounded-lg border p-4 transition-all hover:bg-accent group relative",
                    selectedId === item.id ? "bg-accent border-primary/50 shadow-sm" : "bg-card border-border hover:border-border/80"
                  )}
                >
                  <div className="flex justify-between items-start mb-2 gap-2">
                    <span className="font-semibold line-clamp-1 text-sm flex-1">{item.title || "Untitled Experiment"}</span>
                    <Badge variant="outline" className={cn("text-[10px] px-1 py-0 h-5 shrink-0", getStatusColor(item.status))}>
                      {item.status || "Draft"}
                    </Badge>
                  </div>
                  <div className="text-xs text-muted-foreground flex items-center justify-between">
                    <span className="font-mono opacity-70">{item.id.slice(0, 8)}...</span>
                    <span>{item.updated_at ? new Date(item.updated_at * 1000).toLocaleDateString() : ""}</span>
                  </div>
                  {selectedId === item.id && (
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-l-lg" />
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Log Viewer */}
        <div className="flex-1 flex flex-col bg-card/30 rounded-xl border border-border/50 overflow-hidden shadow-sm">
          {selectedId ? (
            <>
              <div className="border-b p-4 flex justify-between items-center bg-card/50 backdrop-blur-sm">
                <div className="flex items-center gap-2">
                  <Terminal className="h-4 w-4 text-muted-foreground" />
                  <span className="font-mono text-sm">{selectedId}</span>
                </div>
                <div className="text-xs text-muted-foreground">
                  {lines.length} lines loaded
                </div>
              </div>
              
              <div className="flex-1 bg-black/90 p-4 overflow-y-auto font-mono text-xs text-green-400 border border-border/50 shadow-inner">
                {logsLoading && lines.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-muted-foreground">
                    <RefreshCw className="h-6 w-6 animate-spin mr-2" /> Loading logs...
                  </div>
                ) : lines.length > 0 ? (
                  <div className="whitespace-pre-wrap">
                    {lines.join("\n")}
                  </div>
                ) : (
                  <div className="text-muted-foreground opacity-50 italic">No logs available for this experiment.</div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground bg-muted/5">
              <Terminal className="h-16 w-16 mb-4 opacity-20" />
              <p className="text-lg font-medium">Select an experiment</p>
              <p className="text-sm opacity-60">Choose an item from the sidebar to view logs</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
