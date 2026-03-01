"use client"

import { useEffect, useRef } from "react"
import { useMaars } from "../context/MaarsContext"
import {
  fetchLayout,
  generateExecutionFromPlan,
} from "../api"
import type { Layout, LayoutEdge, LayoutNode } from "../types"

const EVENTS_URL = "/api/maars/events"

/** Extract flat layout from backend response (may be nested { treeData, layout }). */
function normalizeLayout(raw: unknown): Layout | null {
  const isRecord = (v: unknown): v is Record<string, unknown> =>
    !!v && typeof v === "object" && !Array.isArray(v)

  const isLayoutNode = (v: unknown): v is LayoutNode => {
    if (!isRecord(v)) return false
    return (
      typeof v.x === "number" &&
      typeof v.y === "number" &&
      typeof v.w === "number" &&
      typeof v.h === "number"
    )
  }

  const isLayoutNodes = (v: unknown): v is Record<string, LayoutNode> => {
    if (!isRecord(v)) return false
    for (const node of Object.values(v)) {
      if (!isLayoutNode(node)) return false
    }
    return true
  }

  const isLayoutEdge = (v: unknown): v is LayoutEdge => {
    if (!isRecord(v)) return false
    const from = v.from
    const to = v.to

    const isStrOrStrArray = (x: unknown) =>
      typeof x === "string" ||
      (Array.isArray(x) && x.every((i) => typeof i === "string"))

    return isStrOrStrArray(from) && isStrOrStrArray(to)
  }

  const isLayoutEdges = (v: unknown): v is LayoutEdge[] =>
    Array.isArray(v) && v.every(isLayoutEdge)

  const coerce = (v: unknown): Layout | null => {
    if (!isRecord(v)) return null
    const nodesRaw = v.nodes
    const edgesRaw = v.edges
    if (!isLayoutNodes(nodesRaw) || !isLayoutEdges(edgesRaw)) return null

    const nodes = nodesRaw
    const edges = edgesRaw

    // Some backend responses might omit width/height; estimate from nodes.
    let maxX = 0
    let maxY = 0
    for (const n of Object.values(nodes)) {
      maxX = Math.max(maxX, n.x + n.w)
      maxY = Math.max(maxY, n.y + n.h)
    }

    const width = typeof v.width === "number" ? v.width : maxX
    const height = typeof v.height === "number" ? v.height : maxY

    return { nodes, edges, width, height }
  }

  if (!isRecord(raw)) return null

  // Backend may send { treeData, layout }
  if (raw.layout != null) {
    const nested = coerce(raw.layout)
    if (nested) return nested
  }

  // Or just the layout itself
  return coerce(raw)
}

export function useMaarsSSE(planId: string | null) {
  const { dispatch } = useMaars()
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    // Important: connect even when planId is null.
    // The planId is only known after /plan/run completes, but we need SSE events
    // (plan-start, plan-tree-update, plan-complete) during the run to populate UI.
    const url = planId
      ? `${EVENTS_URL}?planId=${encodeURIComponent(planId)}`
      : EVENTS_URL
    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => {
      // Connected
    }

    es.addEventListener("plan-start", () => {
      dispatch({ type: "CLEAR_THINKING" })
      dispatch({ type: "SET_TREE", treeData: [], layout: null })
    })

    es.addEventListener("plan-thinking", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data || "{}")
        const { chunk, taskId, operation, scheduleInfo } = data
        if (!chunk && scheduleInfo?.tool_name) {
          dispatch({
            type: "APPEND_THINKING",
            block: {
              key: `schedule_${Date.now()}`,
              blockType: "schedule",
              scheduleInfo,
            },
          })
        } else if (chunk) {
          if (taskId == null) {
            dispatch({
              type: "APPEND_PLAN_CHUNK",
              content: chunk,
              scheduleInfo: scheduleInfo || null,
            })
          } else {
            const key = `${taskId}::${operation || ""}`
            dispatch({
              type: "UPDATE_THINKING",
              key,
              content: chunk,
              scheduleInfo: scheduleInfo || null,
            })
          }
        }
      } catch {
        // ignore parse errors
      }
    })

    es.addEventListener("plan-tree-update", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data || "{}")
        if (data.treeData) {
          dispatch({
            type: "SET_TREE",
            treeData: data.treeData,
            layout: normalizeLayout(data.layout) ?? null,
          })
        }
      } catch {
        // ignore
      }
    })

    es.addEventListener("plan-complete", async (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data || "{}")
        if (data.treeData) {
          dispatch({
            type: "SET_TREE",
            treeData: data.treeData,
            layout: normalizeLayout(data.layout) ?? null,
          })
        }
        if (data.planId) dispatch({ type: "SET_PLAN_ID", planId: data.planId })
        dispatch({ type: "SET_QUALITY", score: data.qualityScore ?? null, comment: data.qualityComment ?? null })
        dispatch({ type: "SET_PLAN_RUNNING", running: false })

        // Generate execution layout
        if (data.planId) {
          try {
            const genRes = await generateExecutionFromPlan(data.planId)
            const execution = genRes.execution
            if (execution?.tasks?.length) {
              const layoutRes = await fetchLayout(execution, data.planId)
              dispatch({ type: "SET_EXECUTION", execution })
              dispatch({ type: "SET_EXECUTION_LAYOUT", layout: layoutRes.layout })
            }
          } catch {
            // best-effort
          }
        }
      } catch {
        dispatch({ type: "SET_PLAN_RUNNING", running: false })
      }
    })

    es.addEventListener("plan-error", () => {
      dispatch({ type: "SET_PLAN_RUNNING", running: false })
    })

    es.addEventListener("execution-layout", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data || "{}")
        const layout = normalizeLayout(data.layout ?? data)
        if (layout) {
          dispatch({ type: "SET_EXECUTION_LAYOUT", layout })
        }
      } catch {
        // ignore
      }
    })

    es.addEventListener("task-states-update", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data || "{}")
        const tasks = data.tasks || []
        if (tasks.length) {
          dispatch({
            type: "TASK_STATES_BATCH",
            updates: tasks.map((t: { task_id: string; status: string }) => ({
              taskId: t.task_id,
              status: t.status,
            })),
          })
        }
      } catch {
        // ignore
      }
    })

    es.addEventListener("task-thinking", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data || "{}")
        const { chunk, taskId, operation, scheduleInfo } = data
        if (chunk) {
          const key = (taskId != null && operation != null) ? `${taskId}::${operation}` : "_default"
          dispatch({
            type: "UPDATE_THINKING",
            key,
            content: chunk,
            scheduleInfo: scheduleInfo || null,
          })
        }
      } catch {
        // ignore
      }
    })

    es.addEventListener("task-output", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data || "{}")
        if (data.taskId != null) {
          dispatch({ type: "SET_TASK_OUTPUT", taskId: data.taskId, output: data.output })
        }
      } catch {
        // ignore
      }
    })

    es.addEventListener("execution-error", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data || "{}")
        const isStopped = (data.error || "").includes("stopped by user")
        if (!isStopped) {
          console.error("Execution error:", data.error)
        }
      } catch {
        // ignore
      }
      dispatch({ type: "SET_EXECUTION_RUNNING", running: false })
    })

    es.addEventListener("execution-complete", () => {
      dispatch({ type: "SET_EXECUTION_RUNNING", running: false })
    })

    es.onerror = () => {
      // EventSource will auto-reconnect
    }

    return () => {
      es.close()
      esRef.current = null
    }
  }, [planId, dispatch])
}
