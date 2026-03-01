"use client"

import { useCallback } from "react"
import { useMaars } from "../context/MaarsContext"
import {
  fetchPlans,
  fetchPlan,
  fetchPlanTree,
  fetchPlanOutputs,
  fetchExecution,
  generateExecutionFromPlan,
  fetchLayout,
  runPlan,
  stopPlan,
  runExecution,
  stopExecution,
  retryTask,
  resumeFromTask,
} from "../api"

export function useMaarsApi() {
  const { planId, dispatch } = useMaars()

  const resolvePlanId = useCallback(async (): Promise<string> => {
    const { planIds } = await fetchPlans()
    if (planIds.length > 0) {
      const id = planIds[0]
      dispatch({ type: "SET_PLAN_ID", planId: id })
      return id
    }
    return planId || "test"
  }, [planId, dispatch])

  const restoreRecentPlan = useCallback(async () => {
    dispatch({ type: "CLEAR_THINKING" })
    const { planIds } = await fetchPlans()
    if (planIds.length === 0) throw new Error("No task to restore")
    const id = planIds[0]
    dispatch({ type: "SET_PLAN_ID", planId: id })

    const [planRes, treeRes, execRes] = await Promise.all([
      fetchPlan(id),
      fetchPlanTree(id),
      fetchExecution(id),
    ])

    const plan = planRes.plan
    const { treeData, layout } = treeRes
    let execution = execRes.execution

    if (plan?.idea) {
      dispatch({ type: "SET_IDEA", idea: plan.idea })
    }

    if (treeData.length) {
      dispatch({ type: "SET_TREE", treeData, layout })
      if (plan?.qualityScore != null) {
        dispatch({ type: "SET_QUALITY", score: plan.qualityScore, comment: plan.qualityComment ?? null })
      }
    }

    if (!execution?.tasks?.length) {
      const genRes = await generateExecutionFromPlan(id)
      execution = genRes.execution
    }

    if (execution?.tasks?.length) {
      const layoutRes = await fetchLayout(execution, id)
      dispatch({ type: "SET_EXECUTION", execution })
      dispatch({ type: "SET_EXECUTION_LAYOUT", layout: layoutRes.layout })
    }

    const outRes = await fetchPlanOutputs(id)
    const outputs = outRes.outputs || {}
    Object.entries(outputs).forEach(([taskId, out]) => {
      const val = out && typeof out === "object" && "content" in out ? (out as { content: unknown }).content : out
      dispatch({ type: "SET_TASK_OUTPUT", taskId, output: val })
    })

    return { planId: id }
  }, [dispatch])

  const generatePlan = useCallback(
    async (idea: string, signal?: AbortSignal) => {
      dispatch({ type: "SET_PLAN_RUNNING", running: true })
      dispatch({ type: "CLEAR_THINKING" })
      dispatch({ type: "SET_TREE", treeData: [], layout: null })
      dispatch({ type: "SET_EXECUTION_LAYOUT", layout: null })

      try {
        const { planId: newId } = await runPlan(idea, signal)
        dispatch({ type: "SET_PLAN_ID", planId: newId })

        // Fallback: fetch plan tree so the UI populates even if SSE events were missed.
        try {
          const [planRes, treeRes] = await Promise.all([
            fetchPlan(newId),
            fetchPlanTree(newId),
          ])
          if (planRes?.plan?.idea) {
            dispatch({ type: "SET_IDEA", idea: planRes.plan.idea })
          }
          dispatch({
            type: "SET_TREE",
            treeData: treeRes.treeData,
            layout: treeRes.layout,
          })
          if (planRes?.plan?.qualityScore != null) {
            dispatch({ type: "SET_QUALITY", score: planRes.plan.qualityScore, comment: planRes.plan.qualityComment ?? null })
          }
        } catch {
          // best-effort; SSE will still update when available
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") return
        throw err
      } finally {
        dispatch({ type: "SET_PLAN_RUNNING", running: false })
      }
    },
    [dispatch]
  )

  const stopPlanRun = useCallback(async () => {
    await stopPlan()
    dispatch({ type: "SET_PLAN_RUNNING", running: false })
  }, [dispatch])

  const generateExecutionLayout = useCallback(async () => {
    if (!planId) return
    const genRes = await generateExecutionFromPlan(planId)
    const execution = genRes.execution
    if (!execution?.tasks?.length) throw new Error("No atomic tasks. Plan first.")
    const layoutRes = await fetchLayout(execution, planId)
    dispatch({ type: "SET_EXECUTION_LAYOUT", layout: layoutRes.layout })
  }, [planId, dispatch])

  const startExecution = useCallback(async () => {
    if (!planId) return
    dispatch({ type: "SET_EXECUTION_RUNNING", running: true })
    try {
      await runExecution(planId)
    } catch (err) {
      dispatch({ type: "SET_EXECUTION_RUNNING", running: false })
      throw err
    }
  }, [planId, dispatch])

  const stopExecutionRun = useCallback(async () => {
    await stopExecution()
    dispatch({ type: "SET_EXECUTION_RUNNING", running: false })
  }, [dispatch])

  const handleRetryTask = useCallback(
    async (taskId: string) => {
      if (!planId) return
      await retryTask(planId, taskId)
      dispatch({ type: "SET_EXECUTION_RUNNING", running: true })
    },
    [planId, dispatch]
  )

  const handleResumeFromTask = useCallback(
    async (taskId: string) => {
      if (!planId) return
      await resumeFromTask(planId, taskId)
      dispatch({ type: "SET_EXECUTION_RUNNING", running: true })
    },
    [planId, dispatch]
  )

  return {
    resolvePlanId,
    restoreRecentPlan,
    generatePlan,
    stopPlanRun,
    generateExecutionLayout,
    startExecution,
    stopExecutionRun,
    retryTask: handleRetryTask,
    resumeFromTask: handleResumeFromTask,
  }
}
