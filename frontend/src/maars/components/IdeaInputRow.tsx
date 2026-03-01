"use client"

import { useCallback, useEffect, useState } from "react"
import { Loader2, Square } from "lucide-react"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { useMaars } from "../context/MaarsContext"
import { useMaarsApi } from "../hooks/useMaarsApi"
import { useMaarsSSE } from "../hooks/useMaarsSSE"
import { api } from "@/lib/api"

export function IdeaInputRow() {
  const { idea, setIdea, planRunning, executionRunning, planId, dispatch } = useMaars()
  const [loadIdeaLoading, setLoadIdeaLoading] = useState(false)
  const {
    restoreRecentPlan,
    generatePlan,
    stopPlanRun,
    generateExecutionLayout,
    startExecution,
    stopExecutionRun,
  } = useMaarsApi()

  useMaarsSSE(planId)

  useEffect(() => {
    restoreRecentPlan().catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps -- run once on mount

  const handleLoadIdea = useCallback(async () => {
    setLoadIdeaLoading(true)
    try {
      const listRes = await api<{ files?: { filename?: string; name?: string }[] }>("ideas/snapshots")
      const files = listRes.files || []
      if (!files.length) {
        const defaultIdea = "Compare Python vs JavaScript for backend development: define evaluation criteria (JSON), research each ecosystem (runtime, frameworks, tooling), and produce a comparison report with pros/cons and scenario-based recommendation."
        setIdea(defaultIdea)
        return
      }
      const latest = files[0].filename || files[0].name || String(files[0])
      const snap = await api<{
        refinement_data?: string | { title?: string; topic?: string; scope?: string; tldr?: string; abstract?: string }
        results?: { topic?: { title?: string; topic?: string; scope?: string }; ideas?: { title?: string; idea?: string; summary?: string; description?: string }[] }[]
      }>(`ideas/snapshots/${encodeURIComponent(latest)}`)

      let ideaText = ""
      const refinement = snap.refinement_data
      if (refinement) {
        ideaText = typeof refinement === "string"
          ? refinement
          : (refinement.title || refinement.topic || refinement.scope || refinement.tldr || refinement.abstract || "")
      }
      if (!ideaText && Array.isArray(snap.results) && snap.results.length) {
        const first = snap.results[0] || {}
        const topic = first.topic || {}
        ideaText = topic.title || topic.topic || topic.scope || ""
        if (!ideaText && Array.isArray(first.ideas) && first.ideas.length) {
          const ideaItem = first.ideas[0] || {}
          ideaText = ideaItem.title || ideaItem.idea || ideaItem.summary || ideaItem.description || ""
        }
      }
      if (!ideaText) {
        ideaText = JSON.stringify(snap, null, 2).slice(0, 500)
      }
      setIdea(String(ideaText).trim())
    } catch (err) {
      alert("Failed to load idea: " + ((err as Error).message || "Unknown error"))
    } finally {
      setLoadIdeaLoading(false)
    }
  }, [setIdea])

  const handlePlan = useCallback(async () => {
    const trimmed = idea.trim()
    if (!trimmed) {
      alert("Please enter an idea first.")
      return
    }
    try {
      await generatePlan(trimmed)
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        console.error(err)
        alert("Error: " + ((err as Error).message || "Failed to generate plan"))
      }
    }
  }, [idea, generatePlan])

  const handleStopPlan = useCallback(async () => {
    await stopPlanRun()
  }, [stopPlanRun])

  const handleExecute = useCallback(async () => {
    if (!planId) return
    dispatch({ type: "CLEAR_EXECUTION_STATE" })
    try {
      await generateExecutionLayout()
      await startExecution()
    } catch (err) {
      console.error(err)
      alert("Error: " + ((err as Error).message || "Failed to start execution"))
    }
  }, [planId, dispatch, generateExecutionLayout, startExecution])

  const handleStopExecution = useCallback(async () => {
    await stopExecutionRun()
  }, [stopExecutionRun])

  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      <Input
        value={idea}
        onChange={(e) => setIdea(e.target.value)}
        placeholder="Enter your research idea..."
        className="flex-1 min-w-[200px] font-mono"
      />
      <Button variant="outline" size="sm" onClick={handleLoadIdea} disabled={loadIdeaLoading}>
        {loadIdeaLoading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          "Load Idea"
        )}
      </Button>
      <Button
        variant="default"
        size="sm"
        onClick={handlePlan}
        disabled={planRunning || !idea.trim()}
      >
        {planRunning ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Planning...
          </>
        ) : (
          "Plan"
        )}
      </Button>
      {planRunning && (
        <Button variant="destructive" size="sm" onClick={handleStopPlan}>
          <Square className="mr-2 h-4 w-4" />
          Stop
        </Button>
      )}
      <Button
        variant="default"
        size="sm"
        onClick={handleExecute}
        disabled={executionRunning || !planId}
      >
        {executionRunning ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Executing...
          </>
        ) : (
          "Execute"
        )}
      </Button>
      {executionRunning && (
        <Button variant="destructive" size="sm" onClick={handleStopExecution}>
          <Square className="mr-2 h-4 w-4" />
          Stop
        </Button>
      )}
    </div>
  )
}
