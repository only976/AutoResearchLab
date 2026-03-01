"use client"

import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Loader2, Save, RefreshCw, ChevronRight, FileJson, ArrowLeft } from "lucide-react"
import { Button } from "@/components/ui/Button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card"
import { Input } from "@/components/ui/Input"
import { Badge } from "@/components/ui/Badge"
import { cn } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { api } from "@/lib/api"

// Types
type Idea = {
  title?: string
  idea_name?: string
  template_type?: string
  content?: string | object
  [key: string]: any
}

type RefinedTopic = {
  title: string
  tldr: string
  abstract: string
  [key: string]: any
}

type IdeaResult = {
  topic: RefinedTopic
  ideas: Idea[]
}

type Snapshot = {
  filename: string
  title: string
  timestamp: string
}

export default function IdeasPage() {
  const [step, setStep] = useState<1 | 3>(1)
  const [scope, setScope] = useState("")
  const [refinedTopic, setRefinedTopic] = useState<RefinedTopic | null>(null)
  const [results, setResults] = useState<IdeaResult[]>([])
  const [loading, setLoading] = useState(false)
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [saving, setSaving] = useState(false)

  // Load snapshots on mount
  useEffect(() => {
    fetchSnapshots()
  }, [])

  const fetchSnapshots = async () => {
    try {
      const data = await api<{ files?: (string | Snapshot)[] }>("ideas/snapshots")
      const files = data.files || []
      const parsedSnapshots = files.map((f: string | Snapshot) => {
        if (typeof f === "string") return { filename: f, title: f, timestamp: "" }
        return f
      })
      setSnapshots(parsedSnapshots)
    } catch (e) {
      console.error("Failed to load snapshots", e)
    }
  }

  const handleRefine = async () => {
    if (!scope.trim()) return
    setLoading(true)
    try {
      const refined = await api<RefinedTopic>("ideas/refine", {
        method: "POST",
        body: { scope },
      })
      setRefinedTopic(refined)

      const generationScope = JSON.stringify(refined)
      const generated = await api<{ ideas?: Idea[] } | Idea[]>("ideas/generate", {
        method: "POST",
        body: { scope: generationScope },
      })
      const result: IdeaResult = {
        topic: refined,
        ideas: Array.isArray(generated) ? generated : generated.ideas || []
      }
      setResults([result])
      setStep(3)
      fetchSnapshots()
    } catch (e) {
      console.error(e)
      alert("Failed to refine and generate ideas")
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = async () => {
    if (!refinedTopic) return
    setLoading(true)
    try {
      const generationScope = JSON.stringify(refinedTopic)
      const data = await api<{ ideas?: Idea[] } | Idea[]>("ideas/generate", {
        method: "POST",
        body: { scope: generationScope },
      })
      // Structure the result
      const result: IdeaResult = {
        topic: refinedTopic,
        ideas: Array.isArray(data) ? data : data.ideas || []
      }
      setResults([result])
      setStep(3)
      // Refresh snapshots list as it's auto-saved
      fetchSnapshots()
    } catch (e) {
      console.error(e)
      alert("Failed to generate ideas")
    } finally {
      setLoading(false)
    }
  }

  const handleSaveSnapshot = async () => {
    if (!refinedTopic || results.length === 0) return
    setSaving(true)
    try {
      await api("ideas/snapshots", {
        method: "POST",
        body: { refinement_data: refinedTopic, results },
      })
      fetchSnapshots()
      alert("Snapshot saved!")
    } catch (e) {
      console.error(e)
      alert("Failed to save snapshot")
    } finally {
      setSaving(false)
    }
  }

  const loadSnapshot = async (filename: string) => {
    setLoading(true)
    try {
      const data = await api<{ refinement_data?: RefinedTopic; results?: IdeaResult[] }>(
        `ideas/snapshots/${encodeURIComponent(filename)}`
      )
      if (data.refinement_data) setRefinedTopic(data.refinement_data)
      if (data.results) setResults(data.results)
      setStep(3)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const [startingExperiment, setStartingExperiment] = useState<string | null>(null)

  const handleStartExperiment = async (topic: RefinedTopic, idea: Idea, ideaIndex: number) => {
    if (startingExperiment !== null) return

    setStartingExperiment(String(ideaIndex))
    try {
      await api("experiments", {
        method: "POST",
        body: { topic, idea },
      })
      window.location.href = "/experiments"
    } catch (e) {
      console.error(e)
      alert("Failed to start experiment")
      setStartingExperiment(null) // Only reset on error so user doesn't click again during redirect
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PageHeader 
        title="Idea Generator" 
        description="Transform research concepts into executable experiments."
      >
        {step > 1 && (
            <Button variant="outline" onClick={() => setStep(1)} size="sm">
             <ArrowLeft className="mr-2 h-4 w-4" /> Back
           </Button>
        )}
      </PageHeader>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-6">
          <AnimatePresence mode="wait">
            {step === 1 && (
              <motion.div
                key="step1"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="max-w-3xl mx-auto space-y-6"
              >
                <Card className="border-primary/20 bg-card/50 backdrop-blur">
                  <CardHeader>
                    <CardTitle>Research Topic</CardTitle>
                    <CardDescription>Enter your initial research direction or keywords.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <textarea
                      className="flex min-h-[150px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                      placeholder="e.g., Implementing efficient RAG systems for scientific literature..."
                      value={scope}
                      onChange={(e) => setScope(e.target.value)}
                    />
                  </CardContent>
                  <CardFooter>
                    <Button 
                      onClick={handleRefine} 
                      disabled={!scope || loading} 
                      className="w-full"
                      size="lg"
                    >
                      {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                      Refine Topic
                    </Button>
                  </CardFooter>
                </Card>
              </motion.div>
            )}

            {step === 3 && (
              <motion.div
                key="step3"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="space-y-6"
              >
                <div className="flex items-center justify-between">
                   <h2 className="text-xl font-semibold">Generated Ideas</h2>
                   <div className="flex gap-2">
                     <Button variant="outline" onClick={handleGenerate} disabled={loading}>
                       <RefreshCw className="mr-2 h-4 w-4" /> Regenerate
                     </Button>
                     <Button onClick={handleSaveSnapshot} disabled={saving || results.length === 0}>
                       {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                       Save Copy
                     </Button>
                   </div>
                </div>

                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                  {results.flatMap(r => r.ideas).map((idea, idx) => (
                    <motion.div
                      key={idx}
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: idx * 0.1 }}
                    >
                      <Card className="h-full flex flex-col hover:border-primary/50 transition-colors">
                        <CardHeader>
                          <Badge variant="outline" className="w-fit mb-2">{idea.template_type || "Idea"}</Badge>
                          <CardTitle className="text-lg leading-tight">{idea.title || idea.idea_name || `Idea ${idx + 1}`}</CardTitle>
                        </CardHeader>
                        <CardContent className="flex-1">
                          <p className="text-sm text-muted-foreground line-clamp-4">
                            {idea.content && typeof idea.content === "object" 
                              ? JSON.stringify(idea.content).slice(0, 200) 
                              : String(idea.content || "").slice(0, 200)}
                            ...
                          </p>
                        </CardContent>
                        <CardFooter>
                          <Button 
                            className="w-full" 
                            onClick={() => handleStartExperiment(results[0].topic, idea, idx)}
                            disabled={startingExperiment !== null}
                          >
                            {startingExperiment === String(idx) ? (
                              <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Starting...
                              </>
                            ) : (
                              <>
                                Start Experiment <ChevronRight className="ml-2 h-4 w-4" />
                              </>
                            )}
                          </Button>
                        </CardFooter>
                      </Card>
                    </motion.div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="w-80 border-l border-border bg-muted/10 p-4 overflow-y-auto flex flex-col gap-4">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Saved Ideas</h3>
          <div className="space-y-2">
            {snapshots.length === 0 && <div className="text-sm text-muted-foreground">No saved snapshots found.</div>}
            {snapshots.map((file) => (
              <Button
                key={file.filename}
                variant="ghost"
                className="w-full justify-start text-xs h-auto py-2 flex flex-col items-start gap-1 hover:bg-muted"
                onClick={() => loadSnapshot(file.filename)}
              >
                <div className="flex items-center w-full truncate font-medium">
                  <FileJson className="mr-2 h-3 w-3 text-primary shrink-0" />
                  <span className="truncate">{file.title}</span>
                </div>
                {file.timestamp && (
                  <span className="text-[10px] text-muted-foreground pl-5">{file.timestamp}</span>
                )}
              </Button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
