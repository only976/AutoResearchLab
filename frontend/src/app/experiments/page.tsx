"use client"

import { useCallback, useEffect, useState } from "react"
import { useSearchParams, useRouter } from "next/navigation"
import { motion, AnimatePresence } from "framer-motion"
import { 
  FlaskConical, 
  Search, 
  Plus, 
  Play, 
  RotateCw, 
  Terminal, 
  FileJson, 
  Files, 
  Clock, 
  CheckCircle2, 
  XCircle, 
  AlertCircle,
  ChevronRight,
  ListTodo,
  History,
  FileText,
  MoreVertical,
  Loader2
} from "lucide-react"
import { Button } from "@/components/ui/Button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card"
import { Input } from "@/components/ui/Input"
import { Badge } from "@/components/ui/Badge"
import { Progress } from "@/components/ui/Progress"
import { cn } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"

// Types
type ExperimentItem = {
  id: string
  title: string
  status: string
  updated_at?: number
  created_at?: string
}

type ExperimentStatus = {
  experiment_status?: string
  current_step?: number
  total_steps?: number
  step_name?: string
  status?: string // 'running', 'completed', 'failed'
  details?: string
}

type ExperimentMeta = {
  id?: string
  idea?: { title?: string; [key: string]: any }
  topic?: { title?: string; [key: string]: any }
  [key: string]: any
}

type ExperimentPlan = {
  steps?: { name: string; description: string; [key: string]: any }[]
  [key: string]: any
}

type ExperimentHistoryItem = {
  step?: string
  status?: string
  output?: string
  timestamp?: number
  [key: string]: any
}

export default function ExperimentsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [items, setItems] = useState<ExperimentItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState("")

  // Detail State
  const [meta, setMeta] = useState<ExperimentMeta | null>(null)
  const [status, setStatus] = useState<ExperimentStatus | null>(null)
  const [plan, setPlan] = useState<ExperimentPlan | null>(null)
  const [history, setHistory] = useState<ExperimentHistoryItem[]>([])
  const [conclusion, setConclusion] = useState<string | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [artifacts, setArtifacts] = useState<string[]>([])
  
  const [activeTab, setActiveTab] = useState<"overview" | "plan" | "history" | "conclusion" | "logs" | "artifacts">("overview")
  const [detailLoading, setDetailLoading] = useState(false)
  const [planLoading, setPlanLoading] = useState(false)

  // Fetch List
  const fetchExperiments = useCallback(async () => {
    try {
      const res = await fetch("/api/experiments")
      if (res.ok) {
        const data = await res.json()
        setItems(data)
        
        // Auto-select logic
        const paramId = searchParams.get("id")
        if (paramId && data.find((i: ExperimentItem) => i.id === paramId)) {
          setSelectedId(paramId)
        } else if (!selectedId && data.length > 0) {
          setSelectedId(data[0].id)
        }
      }
    } catch (e) {
      console.error("Failed to fetch experiments", e)
    } finally {
      setLoading(false)
    }
  }, [searchParams, selectedId])

  useEffect(() => {
    fetchExperiments()
  }, [fetchExperiments])

  // Fetch Details
  useEffect(() => {
    if (!selectedId) return

    const fetchDetails = async () => {
      setDetailLoading(true)
      try {
        const [metaRes, statusRes, planRes, historyRes, conclusionRes, logsRes, artifactsRes] = await Promise.all([
          fetch(`/api/experiments/${selectedId}/meta`),
          fetch(`/api/experiments/${selectedId}/status`),
          fetch(`/api/experiments/${selectedId}/plan`),
          fetch(`/api/experiments/${selectedId}/history`),
          fetch(`/api/experiments/${selectedId}/conclusion`),
          fetch(`/api/experiments/${selectedId}/logs`),
          fetch(`/api/experiments/${selectedId}/artifacts`)
        ])

        if (metaRes.ok) setMeta(await metaRes.json())
        if (statusRes.ok) setStatus(await statusRes.json())
        if (planRes.ok) setPlan(await planRes.json())
        if (historyRes.ok) {
            const historyData = await historyRes.json()
            setHistory(Array.isArray(historyData) ? historyData : [])
        }
        if (conclusionRes.ok) {
            const conclusionData = await conclusionRes.text() // Assume text or markdown
            setConclusion(conclusionData)
        }
        if (logsRes.ok) {
            const logData = await logsRes.json()
            setLogs(logData.lines || [])
        }
        if (artifactsRes.ok) {
            const artifactData = await artifactsRes.json()
            setArtifacts(artifactData.files || [])
        }
      } catch (e) {
        console.error("Failed to fetch details", e)
      } finally {
        setDetailLoading(false)
      }
    }

    fetchDetails()
    // Poll for status and logs if running
    const interval = setInterval(() => {
        fetch(`/api/experiments/${selectedId}/status`).then(r => r.json()).then(setStatus).catch(() => {})
        fetch(`/api/experiments/${selectedId}/logs`).then(r => r.json()).then(d => setLogs(d.lines || [])).catch(() => {})
    }, 5000)
    
    return () => clearInterval(interval)
  }, [selectedId])

  const filteredItems = items.filter(item => 
    item.title?.toLowerCase().includes(searchTerm.toLowerCase()) || 
    item.id.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case "completed": return "bg-green-500/10 text-green-500 border-green-500/20"
      case "running": return "bg-blue-500/10 text-blue-500 border-blue-500/20"
      case "failed": return "bg-red-500/10 text-red-500 border-red-500/20"
      default: return "bg-slate-500/10 text-slate-500 border-slate-500/20"
    }
  }

  const runExperiment = async () => {
      if (!selectedId) return
      try {
          await fetch(`/api/experiments/${selectedId}/run`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ max_iterations: 50 })
          })
          // Force refresh status
          const statusRes = await fetch(`/api/experiments/${selectedId}/status`)
          if (statusRes.ok) setStatus(await statusRes.json())
      } catch (e) {
          console.error("Failed to run experiment", e)
      }
  }

  const generatePlan = async () => {
    if (!selectedId || !meta) return
    setPlanLoading(true)
    try {
        const res = await fetch(`/api/experiments/${selectedId}/plan`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                idea: meta.idea,
                topic: meta.topic
            })
        })
        if (res.ok) {
            const data = await res.json()
            setPlan(data)
            setActiveTab("plan")
            // Refresh list to update title if it was missing
            fetchExperiments()
        } else {
            alert("Failed to generate plan")
        }
    } catch (e) {
        console.error("Failed to generate plan", e)
        alert("Failed to generate plan")
    } finally {
        setPlanLoading(false)
    }
  }

  const TabButton = ({ id, label, icon: Icon }: { id: typeof activeTab, label: string, icon: any }) => (
    <button
      onClick={() => setActiveTab(id)}
      className={cn(
        "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
        activeTab === id 
          ? "border-primary text-primary" 
          : "border-transparent text-muted-foreground hover:text-foreground"
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  )

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)]">
      <PageHeader 
        title="Experiments" 
        description="Manage and monitor your automated research experiments."
        className="mb-4 pb-4"
      >
        <Button onClick={() => router.push("/ideas")}>
          <Plus className="mr-2 h-4 w-4" /> New Experiment
        </Button>
      </PageHeader>

      <div className="flex flex-1 gap-6 overflow-hidden">
        {/* Sidebar List */}
        <div className="w-80 flex flex-col gap-4 flex-shrink-0">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input 
              placeholder="Search..." 
              className="pl-9" 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <div className="flex-1 overflow-y-auto space-y-2 pr-2">
            {loading ? (
               <div className="text-center py-8 text-muted-foreground">Loading...</div>
            ) : filteredItems.length === 0 ? (
               <div className="text-center py-8 text-muted-foreground">No experiments found.</div>
            ) : (
              filteredItems.map(item => (
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
                  <div className="text-xs text-muted-foreground flex items-center gap-2">
                    <Clock className="h-3 w-3" />
                    {item.updated_at 
                      ? new Date(item.updated_at * 1000).toLocaleDateString() 
                      : item.created_at 
                        ? new Date(item.created_at).toLocaleDateString()
                        : "Unknown date"}
                  </div>
                  {selectedId === item.id && (
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-l-lg" />
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Detail View */}
        <div className="flex-1 flex flex-col bg-card/30 rounded-xl border border-border/50 overflow-hidden shadow-sm">
          {selectedId && meta ? (
            <>
              {/* Header */}
              <div className="border-b p-6 flex justify-between items-start bg-card/50 backdrop-blur-sm">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                     <h1 className="text-xl font-bold line-clamp-1">{meta.idea?.title || meta.topic?.title || "Untitled Experiment"}</h1>
                     <Badge className={getStatusColor(status?.experiment_status || "draft")}>
                       {status?.experiment_status || "Draft"}
                     </Badge>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground font-mono">
                    <span>ID: {selectedId.slice(0, 8)}</span>
                    <span>Created: {items.find(i => i.id === selectedId)?.created_at || "N/A"}</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  {!plan ? (
                     <Button variant="outline" size="sm" onClick={generatePlan} disabled={planLoading}>
                        {planLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                        Generate Plan
                     </Button>
                  ) : (
                     <Button variant="outline" size="sm" onClick={runExperiment} disabled={status?.experiment_status === "running"}>
                        <Play className="mr-2 h-4 w-4" /> Run
                     </Button>
                  )}
                  <Button variant="outline" size="sm" onClick={() => fetchExperiments()}>
                    <RotateCw className="mr-2 h-4 w-4" /> Refresh
                  </Button>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex border-b bg-muted/20 px-6 overflow-x-auto scrollbar-none">
                <TabButton id="overview" label="Overview" icon={FlaskConical} />
                <TabButton id="plan" label="Plan" icon={ListTodo} />
                <TabButton id="history" label="History" icon={History} />
                <TabButton id="conclusion" label="Conclusion" icon={FileText} />
                <TabButton id="logs" label="Logs" icon={Terminal} />
                <TabButton id="artifacts" label="Artifacts" icon={Files} />
              </div>

              {/* Content */}
              <div className="flex-1 overflow-y-auto p-6 bg-background/50">
                <AnimatePresence mode="wait">
                  {activeTab === "overview" && (
                    <motion.div 
                      key="overview"
                      initial={{ opacity: 0, y: 10 }} 
                      animate={{ opacity: 1, y: 0 }} 
                      exit={{ opacity: 0, y: -10 }}
                      className="space-y-6"
                    >
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                         <Card>
                           <CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Current Step</CardTitle></CardHeader>
                           <CardContent>
                             <div className="flex items-center justify-between mb-2">
                               <div className="text-2xl font-bold">{status?.current_step || 0} <span className="text-muted-foreground text-lg">/ {status?.total_steps || "?"}</span></div>
                               {status?.total_steps && status.total_steps > 0 && (
                                   <span className="text-xs text-muted-foreground font-mono">
                                       {Math.round(((status.current_step || 0) / status.total_steps) * 100)}%
                                   </span>
                               )}
                             </div>
                             <Progress value={status?.total_steps && status.total_steps > 0 ? ((status.current_step || 0) / status.total_steps) * 100 : 0} className="h-2" />
                           </CardContent>
                         </Card>
                         <Card className="md:col-span-2">
                           <CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Current Activity</CardTitle></CardHeader>
                           <CardContent>
                             <div className="text-lg font-medium truncate" title={status?.step_name}>{status?.step_name || "Idle"}</div>
                             <p className="text-xs text-muted-foreground mt-1">{status?.details || "No active process details."}</p>
                           </CardContent>
                         </Card>
                      </div>

                      <Card>
                        <CardHeader>
                          <CardTitle>Experiment Description</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                          <div>
                            <h4 className="text-sm font-medium text-muted-foreground mb-1">Title</h4>
                            <p>{meta.idea?.title || "N/A"}</p>
                          </div>
                          <div>
                            <h4 className="text-sm font-medium text-muted-foreground mb-1">Idea Content</h4>
                             <p className="text-sm text-muted-foreground whitespace-pre-wrap bg-muted/30 p-3 rounded-md">
                                {typeof meta.idea?.content === 'string' ? meta.idea?.content : JSON.stringify(meta.idea?.content || {}, null, 2)}
                             </p>
                          </div>
                        </CardContent>
                      </Card>
                    </motion.div>
                  )}

                  {activeTab === "plan" && (
                    <motion.div 
                      key="plan"
                      initial={{ opacity: 0, y: 10 }} 
                      animate={{ opacity: 1, y: 0 }} 
                      exit={{ opacity: 0, y: -10 }}
                      className="space-y-4"
                    >
                      {plan ? (
                         plan.steps ? (
                            <div className="space-y-4">
                                {plan.steps.map((step, idx) => (
                                    <Card key={idx}>
                                        <CardHeader className="pb-2">
                                            <CardTitle className="text-base flex items-center gap-2">
                                                <Badge variant="outline" className="w-6 h-6 rounded-full flex items-center justify-center p-0">{idx + 1}</Badge>
                                                {step.name}
                                            </CardTitle>
                                        </CardHeader>
                                        <CardContent>
                                            <p className="text-sm text-muted-foreground">{step.description}</p>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                         ) : (
                             <Card>
                                 <CardContent className="p-4">
                                    <pre className="whitespace-pre-wrap font-mono text-xs">{JSON.stringify(plan, null, 2)}</pre>
                                 </CardContent>
                             </Card>
                         )
                      ) : (
                        <div className="text-center py-12 text-muted-foreground">
                          <ListTodo className="h-12 w-12 mx-auto mb-4 opacity-20" />
                          No plan available yet.
                        </div>
                      )}
                    </motion.div>
                  )}

                  {activeTab === "history" && (
                    <motion.div 
                      key="history"
                      initial={{ opacity: 0, y: 10 }} 
                      animate={{ opacity: 1, y: 0 }} 
                      exit={{ opacity: 0, y: -10 }}
                    >
                       {history.length > 0 ? (
                           <div className="relative border-l border-border ml-4 space-y-8 pl-8 py-4">
                               {history.map((item, idx) => (
                                   <div key={idx} className="relative">
                                       <span className="absolute -left-[39px] top-1 h-5 w-5 rounded-full border border-background bg-primary flex items-center justify-center">
                                            <span className="h-2 w-2 rounded-full bg-background" />
                                       </span>
                                       <div className="flex flex-col gap-1">
                                           <span className="text-sm font-medium">{item.step || `Step ${idx + 1}`}</span>
                                           <span className="text-xs text-muted-foreground">{item.timestamp ? new Date(item.timestamp * 1000).toLocaleString() : ""}</span>
                                           <Card className="mt-2">
                                               <CardContent className="p-3 text-xs font-mono bg-muted/50">
                                                   {item.output || item.status || "Completed"}
                                               </CardContent>
                                           </Card>
                                       </div>
                                   </div>
                               ))}
                           </div>
                       ) : (
                        <div className="text-center py-12 text-muted-foreground">
                          <History className="h-12 w-12 mx-auto mb-4 opacity-20" />
                          No execution history available.
                        </div>
                       )}
                    </motion.div>
                  )}

                  {activeTab === "conclusion" && (
                    <motion.div 
                      key="conclusion"
                      initial={{ opacity: 0, y: 10 }} 
                      animate={{ opacity: 1, y: 0 }} 
                      exit={{ opacity: 0, y: -10 }}
                    >
                       {conclusion ? (
                           <Card>
                               <CardContent className="p-6 prose dark:prose-invert max-w-none">
                                   <pre className="whitespace-pre-wrap font-sans">{conclusion}</pre>
                               </CardContent>
                           </Card>
                       ) : (
                        <div className="text-center py-12 text-muted-foreground">
                          <FileText className="h-12 w-12 mx-auto mb-4 opacity-20" />
                          No conclusion generated yet.
                        </div>
                       )}
                    </motion.div>
                  )}

                  {activeTab === "logs" && (
                    <motion.div 
                      key="logs"
                      initial={{ opacity: 0, y: 10 }} 
                      animate={{ opacity: 1, y: 0 }} 
                      exit={{ opacity: 0, y: -10 }}
                      className="h-full flex flex-col"
                    >
                      <div className="bg-black/90 text-green-400 font-mono text-xs p-4 rounded-lg h-full overflow-y-auto whitespace-pre-wrap border border-border/50 shadow-inner">
                        {logs.length > 0 ? logs.join("\n") : "No logs available."}
                      </div>
                    </motion.div>
                  )}

                  {activeTab === "artifacts" && (
                    <motion.div 
                      key="artifacts"
                      initial={{ opacity: 0, y: 10 }} 
                      animate={{ opacity: 1, y: 0 }} 
                      exit={{ opacity: 0, y: -10 }}
                    >
                      {artifacts.length > 0 ? (
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                          {artifacts.map(file => (
                            <Card key={file} className="hover:border-primary cursor-pointer transition-all hover:shadow-md group bg-card/50">
                              <CardContent className="p-6 flex flex-col items-center justify-center gap-4 aspect-square">
                                <div className="p-3 rounded-full bg-primary/10 group-hover:bg-primary/20 transition-colors">
                                    <FileJson className="h-6 w-6 text-primary" />
                                </div>
                                <span className="text-xs text-center font-medium truncate w-full" title={file}>{file}</span>
                              </CardContent>
                            </Card>
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-12 text-muted-foreground">
                          <Files className="h-12 w-12 mx-auto mb-4 opacity-20" />
                          No artifacts generated yet.
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground bg-muted/5">
              <FlaskConical className="h-16 w-16 mb-4 opacity-20" />
              <p className="text-lg font-medium">Select an experiment</p>
              <p className="text-sm opacity-60">Choose an item from the sidebar to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
