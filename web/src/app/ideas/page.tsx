"use client"

import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Loader2, Save, Play, RefreshCw, ChevronRight, FileJson, ArrowLeft } from "lucide-react"
import { Button } from "@/components/ui/Button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card"
import { Input } from "@/components/ui/Input"
import { Badge } from "@/components/ui/Badge"
import { cn } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"

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
}

export default function IdeasPage() {
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [scope, setScope] = useState("")
  const [refinedTopic, setRefinedTopic] = useState<RefinedTopic | null>(null)
  const [results, setResults] = useState<IdeaResult[]>([])
  const [loading, setLoading] = useState(false)
  const [snapshots, setSnapshots] = useState<string[]>([])
  const [saving, setSaving] = useState(false)

  // Load snapshots on mount
  useEffect(() => {
    fetchSnapshots()
  }, [])

  const fetchSnapshots = async () => {
    try {
      const res = await fetch("/api/ideas/snapshots")
      if (res.ok) {
        const data = await res.json()
        setSnapshots(data.files || [])
      }
    } catch (e) {
      console.error("Failed to load snapshots", e)
    }
  }

  const handleRefine = async () => {
    if (!scope.trim()) return
    setLoading(true)
    try {
      const res = await fetch("/api/ideas/refine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope }),
      })
      const data = await res.json()
      setRefinedTopic(data)
      setStep(2)
    } catch (e) {
      console.error(e)
      alert("Failed to refine topic")
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = async () => {
    if (!refinedTopic) return
    setLoading(true)
    try {
      // Use the refined abstract/tldr as the scope for generation
      const generationScope = JSON.stringify(refinedTopic)
      const res = await fetch("/api/ideas/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: generationScope }),
      })
      const data = await res.json()
      // Structure the result
      const result: IdeaResult = {
        topic: refinedTopic,
        ideas: Array.isArray(data) ? data : data.ideas || []
      }
      setResults([result])
      setStep(3)
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
      const res = await fetch("/api/ideas/snapshots", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          refinement_data: refinedTopic,
          results: results
        }),
      })
      if (res.ok) {
        fetchSnapshots()
        alert("Snapshot saved!")
      }
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
      const res = await fetch(`/api/ideas/snapshots/${filename}`)
      if (res.ok) {
        const data = await res.json()
        if (data.refinement_data) setRefinedTopic(data.refinement_data)
        if (data.results) setResults(data.results)
        setStep(3)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const [startingExperiment, setStartingExperiment] = useState<string | null>(null)

  const handleStartExperiment = async (topic: RefinedTopic, idea: Idea, ideaIndex: number) => {
    if (startingExperiment !== null) return // Prevent multiple clicks
    
    setStartingExperiment(String(ideaIndex))
    try {
      const res = await fetch("/api/experiments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: topic,
          idea: idea
        }),
      })
      if (res.ok) {
        // Use router.push for smoother navigation instead of window.location
        // But window.location ensures full reload if state is stale
        window.location.href = "/experiments"
      } else {
        throw new Error("Failed to create experiment")
      }
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
           <Button variant="outline" onClick={() => setStep(step - 1 as 1|2)} size="sm">
             <ArrowLeft className="mr-2 h-4 w-4" /> Back
           </Button>
        )}
      </PageHeader>

      <div className="flex-1">
        <AnimatePresence mode="wait">
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="grid gap-8 lg:grid-cols-3"
            >
              <div className="lg:col-span-2 space-y-6">
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
              </div>

              <div className="space-y-4">
                <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Recent Snapshots</h3>
                <div className="space-y-2">
                  {snapshots.length === 0 && <div className="text-sm text-muted-foreground">No saved snapshots found.</div>}
                  {snapshots.slice(0, 5).map((file) => (
                    <Button
                      key={file}
                      variant="ghost"
                      className="w-full justify-start text-xs truncate"
                      onClick={() => loadSnapshot(file)}
                    >
                      <FileJson className="mr-2 h-3 w-3 text-primary" />
                      <span className="truncate">{file}</span>
                    </Button>
                  ))}
                </div>
              </div>
            </motion.div>
          )}

          {step === 2 && refinedTopic && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="max-w-3xl mx-auto space-y-6"
            >
              <Card className="border-primary/20 bg-card/50 backdrop-blur">
                <CardHeader>
                  <CardTitle>Refined Topic: {refinedTopic.title}</CardTitle>
                  <CardDescription>Review the refined research direction before generating concrete ideas.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="rounded-lg bg-muted/50 p-4 text-sm text-muted-foreground">
                    <span className="font-semibold text-foreground">TL;DR:</span> {refinedTopic.tldr}
                  </div>
                  <div className="text-sm leading-relaxed">
                    {refinedTopic.abstract}
                  </div>
                </CardContent>
                <CardFooter className="flex justify-between gap-4">
                  <Button variant="ghost" onClick={() => setStep(1)}>Edit Topic</Button>
                  <Button onClick={handleGenerate} disabled={loading} size="lg" className="flex-1">
                    {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                    Generate Ideas
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
                     Save Snapshot
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
    </div>
  )
}
