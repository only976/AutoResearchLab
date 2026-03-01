"use client"

import { useState, useCallback, useRef, useEffect } from "react"
import { createPortal } from "react-dom"
import { useMaars } from "../context/MaarsContext"
import { useMaarsApi } from "../hooks/useMaarsApi"
import { escapeHtml } from "../utils/markdown"
import type { Layout, LayoutEdge, LayoutNode, Task } from "../types"
import { cn } from "@/lib/utils"

function buildSmoothPath(pts: [number, number][]): string {
  if (!pts || pts.length < 2) return ""
  const [x1, y1] = pts[0]
  const [x2, y2] = pts[1]
  const my = (y1 + y2) / 2
  return `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`
}

function aggregateStatus(tasks: Task[]): string {
  const hasError = tasks.some(
    (t) => t?.status === "execution-failed" || t?.status === "validation-failed"
  )
  const allDone = tasks.length > 0 && tasks.every((t) => t?.status === "done")
  const allUndone = tasks.length > 0 && tasks.every((t) => !t?.status || t?.status === "undone")
  if (hasError) return "execution-failed"
  if (allDone) return "done"
  if (allUndone) return "undone"
  return "doing"
}

interface TaskTreeProps {
  treeData: Task[]
  layout: Layout | null
  taskById: Map<string, Task>
  isExecution: boolean
}

export function TaskTree({ treeData, layout, taskById, isExecution }: TaskTreeProps) {
  const { taskStatusMap, dispatch } = useMaars()
  const { retryTask, resumeFromTask } = useMaarsApi()
  const [popover, setPopover] = useState<{
    tasks: Task[]
    anchor: { left: number; right: number; top: number; bottom: number; width: number; height: number }
  } | null>(null)
  const [rollbackTaskId, setRollbackTaskId] = useState<string | null>(null)
  const rollbackTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(
    () => () => {
      if (rollbackTimeoutRef.current) clearTimeout(rollbackTimeoutRef.current)
    },
    []
  )

  const getStatus = useCallback(
    (taskId: string, task?: Task): string => {
      return taskStatusMap[taskId] ?? task?.status ?? "undone"
    },
    [taskStatusMap]
  )

  const handleNodeClick = useCallback(
    (e: React.MouseEvent, tasks: Task[]) => {
      e.stopPropagation()
      const rect = (e.target as HTMLElement).getBoundingClientRect()
      const ids = (a: Task[]) => a.map((t) => t.task_id).sort().join(",")
      setPopover((prev) => {
        const isSameNode = prev && ids(prev.tasks) === ids(tasks)
        return isSameNode
          ? null
          : {
              tasks,
              anchor: {
                left: rect.left,
                right: rect.right,
                top: rect.top,
                bottom: rect.bottom,
                width: rect.width,
                height: rect.height,
              },
            }
      })
    },
    []
  )

  const handleRetry = useCallback(
    async (taskId: string) => {
      if (rollbackTimeoutRef.current) clearTimeout(rollbackTimeoutRef.current)
      setRollbackTaskId(taskId)
      rollbackTimeoutRef.current = setTimeout(() => {
        setRollbackTaskId(null)
        rollbackTimeoutRef.current = null
      }, 3000)
      try {
        await retryTask(taskId)
        setPopover(null)
      } catch (err) {
        console.error(err)
        setRollbackTaskId(null)
        if (rollbackTimeoutRef.current) {
          clearTimeout(rollbackTimeoutRef.current)
          rollbackTimeoutRef.current = null
        }
        alert("Failed: " + (err as Error).message)
      }
    },
    [retryTask]
  )

  const handleResume = useCallback(
    async (taskId: string) => {
      try {
        await resumeFromTask(taskId)
        setPopover(null)
      } catch (err) {
        console.error(err)
        alert("Failed: " + (err as Error).message)
      }
    },
    [resumeFromTask]
  )

  // Backend may return { treeData, layout: { nodes, edges, width, height } }; extract inner layout
  const actualLayout =
    layout && typeof layout === "object" && "layout" in layout && layout.layout && "nodes" in (layout.layout as object)
      ? (layout.layout as Layout)
      : (layout as Layout | null)

  const edges = actualLayout?.edges ?? []

  // Glow type: undone→doing = yellow on upstream; red only on error rollback (user clicked Retry)
  const edgeGlowType = useCallback(
    (edge: LayoutEdge): "yellow" | "red" | null => {
      if (!isExecution) return null
      const fromIds = Array.isArray(edge.from) ? edge.from : edge.from ? [edge.from] : []
      const toIds = Array.isArray(edge.to) ? edge.to : edge.to ? [edge.to] : []
      const ids = [...fromIds, ...toIds]
      if (rollbackTaskId && ids.includes(rollbackTaskId)) return "red"
      const hasDoingTarget = toIds.some((id) => getStatus(id, taskById.get(id)) === "doing")
      if (hasDoingTarget) return "yellow"
      return null
    },
    [isExecution, taskById, getStatus, rollbackTaskId]
  )

  // Decomposition: leaf = no outgoing edges. Execution: no leaf styling for single nodes.
  const isLeafNode = useCallback(
    (taskId: string) => {
      if (isExecution) return false
      const fromIds = (e: LayoutEdge) =>
        Array.isArray(e.from) ? e.from : e.from ? [e.from] : []
      return !edges.some((e) => fromIds(e).includes(taskId))
    },
    [edges, isExecution]
  )

  if (!actualLayout || !treeData.length) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
        No tasks to display
      </div>
    )
  }

  const { nodes = {}, width: layoutWidth = 0, height: layoutHeight = 0 } = actualLayout
  const width = Math.max(layoutWidth, 1)
  const height = Math.max(layoutHeight, 1)

  return (
    <div className="relative flex-1 min-h-0 overflow-auto">
      <div
        className="relative overflow-visible"
        style={{
          width: `${width}px`,
          height: `${height}px`,
          minWidth: `${width}px`,
          minHeight: `${height}px`,
        }}
      >
        {/* SVG 和节点必须在同一坐标系的同一容器内叠加 */}
        <svg
          className="absolute top-0 left-0 pointer-events-none"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          style={{ display: "block" }}
        >
          <defs>
            <filter id="edge-glow" filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse" x={-100} y={-100} width={width + 200} height={height + 200}>
              <feGaussianBlur in="SourceGraphic" stdDeviation="1.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          {(edges || []).map((edge: LayoutEdge, i) => {
            const pts = edge.points
            if (!pts || pts.length < 2) return null
            const d = buildSmoothPath(pts)
            const isCrossStage = isExecution && edge.adjacent === false
            const glowType = isExecution ? edgeGlowType(edge) : null
            if (isExecution) {
              const glowStroke =
                glowType === "red"
                  ? "hsl(var(--destructive))"
                  : glowType === "yellow"
                    ? "hsl(45 93% 47%)"
                    : undefined
              return (
                <g key={i}>
                  {/* Glow on status change: yellow (doing), red (error); includes cross-stage */}
                  {glowType && (
                    <path
                      d={d}
                      fill="none"
                      stroke={glowStroke}
                      strokeWidth={isCrossStage ? 2 : 2.5}
                      strokeDasharray={isCrossStage ? "4 3" : "none"}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      filter="url(#edge-glow)"
                      className="tree-edge-glow-on-active"
                    />
                  )}
                  {/* Main stroke: cross-stage = reduced presence */}
                  <path
                    d={d}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={isCrossStage ? 1 : 1.5}
                    strokeDasharray={isCrossStage ? "4 3" : "none"}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={cn(
                      "tree-edge-path text-muted-foreground/50",
                      isCrossStage && "opacity-35"
                    )}
                  />
                </g>
              )
            }
            return (
              <path
                key={i}
                d={d}
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
                className="tree-edge-path text-muted-foreground/50"
              />
            )
          })}
        </svg>

        <div
          className="absolute top-0 left-0"
          style={{ width: `${width}px`, height: `${height}px` }}
        >
          {Object.entries(nodes).map(([taskId, pos]) => {
              const ids = (pos as LayoutNode & { ids?: string[] }).ids
              const isMerged = ids && ids.length >= 2 && isExecution

              if (isMerged) {
                const taskDatas = ids.map((id) => taskById.get(id) || { task_id: id })
                const status = aggregateStatus(taskDatas)
                return (
                  <div
                    key={taskId}
                    className={cn(
                      "absolute tree-task tree-task-merged cursor-pointer rounded-md border border-border px-2 py-1 text-xs font-medium truncate flex items-center justify-center",
                      "bg-background border-border hover:border-primary/50",
                      status !== "undone" && `task-status-${status}`
                    )}
                    style={{
                      position: "absolute",
                      left: pos.x,
                      top: pos.y,
                      width: pos.w,
                      height: pos.h,
                    }}
                    title={ids.join(", ")}
                    onClick={(e) => handleNodeClick(e, taskDatas)}
                  >
                    <span className="pointer-events-auto">{ids.length}</span>
                  </div>
                )
              }

              const task = taskById.get(taskId)
              if (!task) return null
              const status = getStatus(taskId, task)
              const desc = (task.description || task.objective || "").trim() || taskId || "Task"

              return (
                <div
                  key={taskId}
                  className={cn(
                    "absolute tree-task cursor-pointer rounded-md border border-border px-2 py-1 text-xs font-medium truncate",
                    "bg-background border-border hover:border-primary/50",
                    isExecution && status !== "undone" && `task-status-${status}`,
                    !isExecution && isLeafNode(taskId) && "tree-task-leaf"
                  )}
                  style={{
                    position: "absolute",
                    left: pos.x,
                    top: pos.y,
                    width: pos.w,
                    height: pos.h,
                  }}
                  title={desc}
                  onClick={(e) => handleNodeClick(e, [task])}
                >
                  {/* 普通节点不显示文本，仅合并节点显示数量 */}
                </div>
              )
            })}
        </div>
      </div>

      {popover &&
        typeof document !== "undefined" &&
        (() => {
          const POPOVER_W = 220
          const POPOVER_MAX_H = 360
          const GAP = 8
          const r = popover.anchor
          const vw = window.innerWidth
          const vh = window.innerHeight
          // 优先在节点右侧，空间不足则放左侧
          let left = r.right + GAP
          if (left + POPOVER_W > vw - GAP) {
            left = r.left - POPOVER_W - GAP
          }
          if (left < GAP) left = GAP
          if (left + POPOVER_W > vw - GAP) left = vw - POPOVER_W - GAP
          // 垂直：优先在节点下方，空间不足则放上方。用 bottom 定位“上方”时可不依赖弹窗高度
          type VerticalStyle = { top?: number; bottom?: number }
          let vertical: VerticalStyle
          if (r.bottom + POPOVER_MAX_H + GAP <= vh) {
            vertical = { top: r.bottom + GAP }
          } else if (r.top - GAP - POPOVER_MAX_H >= GAP) {
            vertical = { bottom: vh - (r.top - GAP) }
          } else {
            const centerTop = r.top + r.height / 2 - 80
            vertical = { top: Math.max(GAP, Math.min(centerTop, vh - POPOVER_MAX_H - GAP)) }
          }
          return createPortal(
          <>
            <div
              style={{
                position: "fixed",
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                zIndex: 9998,
                cursor: "default",
              }}
              onClick={() => setPopover(null)}
              onMouseDown={() => setPopover(null)}
              aria-hidden="true"
            />
            <div
              className="bg-background border border-border rounded-md shadow-xl p-4 overflow-y-auto"
              style={{
                position: "fixed",
                zIndex: 9999,
                width: POPOVER_W,
                maxHeight: POPOVER_MAX_H,
                left,
                ...vertical,
              }}
              role="dialog"
              aria-label="Task details"
            >
              {popover.tasks.length === 1 ? (
                <TaskDetailBody
                  task={popover.tasks[0]}
                  onRetry={handleRetry}
                  onResume={handleResume}
                />
              ) : (
                <div className="space-y-2">
                  {popover.tasks.map((t) => (
                    <TaskDetailBody
                      key={t.task_id}
                      task={t}
                      onRetry={handleRetry}
                      onResume={handleResume}
                    />
                  ))}
                </div>
              )}
            </div>
          </>,
          document.body
          )
        })()}
    </div>
  )
}

function TaskDetailBody({
  task,
  onRetry,
  onResume,
}: {
  task: Task
  onRetry: (id: string) => void
  onResume: (id: string) => void
}) {
  const desc = (task.description || task.objective || "").trim() || "-"
  const deps = (task.dependencies || []).length > 0 ? (task.dependencies || []).join(", ") : "None"
  const hasStatus = task.status != null
  const status = task.status || "undone"
  const isFailed = status === "execution-failed" || status === "validation-failed"
  const isUndone = !status || status === "undone"
  const hasInputOutput = task.input && task.output
  const out = task.output || {}
  const outputDesc = hasInputOutput
    ? [out.artifact || out.description, out.format].filter(Boolean).join(" · ") || "-"
    : "-"

  return (
    <div className="space-y-2 text-sm break-words">
      <div className="font-medium">{escapeHtml(task.task_id)}</div>
      <div>
        <span className="text-muted-foreground">Description:</span> {escapeHtml(desc)}
      </div>
      <div>
        <span className="text-muted-foreground">Dependencies:</span> {escapeHtml(deps)}
      </div>
      {hasStatus && (
        <div>
          <span className="text-muted-foreground">Status:</span>{" "}
          <span className={cn("task-status", `task-status-${status}`)}>{escapeHtml(status)}</span>
        </div>
      )}
      {hasInputOutput && (
        <>
          <div>
            <span className="text-muted-foreground">Input:</span>{" "}
            {escapeHtml(task.input?.description || "-")}
          </div>
          <div>
            <span className="text-muted-foreground">Output:</span> {escapeHtml(outputDesc)}
          </div>
        </>
      )}
      {task.validation && (
        <div>
          <span className="text-muted-foreground">Validation:</span>{" "}
          {task.validation.description
            ? escapeHtml(task.validation.description)
            : task.validation.criteria?.length
              ? escapeHtml((task.validation.criteria || []).join("; "))
              : "-"}
        </div>
      )}
      {isFailed && (
        <button
          type="button"
          className="rounded-md border border-border px-2 py-1 text-xs hover:bg-muted"
          onClick={() => onRetry(task.task_id)}
        >
          Retry
        </button>
      )}
      {isUndone && (
        <button
          type="button"
          className="rounded-md border border-border px-2 py-1 text-xs hover:bg-muted"
          onClick={() => onResume(task.task_id)}
        >
          Run from here
        </button>
      )}
    </div>
  )
}
