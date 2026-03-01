"use client"

import { useState, useCallback } from "react"
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
    anchor: { x: number; y: number }
  } | null>(null)

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
      setPopover((prev) =>
        prev && prev.tasks === tasks ? null : { tasks, anchor: { x: rect.right, y: rect.top + rect.height / 2 } }
      )
    },
    []
  )

  const handleRetry = useCallback(
    async (taskId: string) => {
      try {
        await retryTask(taskId)
        setPopover(null)
      } catch (err) {
        console.error(err)
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

  if (!layout || !treeData.length) {
    return (
      <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
        No tasks to display
      </div>
    )
  }

  const { nodes, edges, width, height } = layout

  return (
    <div className="relative flex-1 min-h-0 overflow-auto">
      <div
        className="relative"
        style={{ width: `${width}px`, height: `${height}px`, minHeight: `${height}px` }}
      >
        <svg
          className="absolute inset-0 pointer-events-none"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
        >
          {(edges || []).map((edge: LayoutEdge, i) => {
            const pts = edge.points
            if (!pts || pts.length < 2) return null
            const d = buildSmoothPath(pts)
            return (
              <path
                key={i}
                d={d}
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
                className={cn(
                  "text-muted-foreground/50",
                  isExecution && edge.adjacent === false && "opacity-60"
                )}
              />
            )
          })}
        </svg>

        <div className="absolute inset-0">
          <div className="absolute top-0 left-0" style={{ width: `${width}px`, height: `${height}px` }}>
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
                      "absolute tree-task tree-task-leaf tree-task-merged cursor-pointer rounded border px-2 py-1 text-xs font-medium truncate flex items-center justify-center",
                      "bg-background border-border hover:border-primary/50",
                      status !== "undone" && `task-status-${status}`
                    )}
                    style={{
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
                    "absolute tree-task cursor-pointer rounded border px-2 py-1 text-xs font-medium truncate",
                    "bg-background border-border hover:border-primary/50",
                    isExecution && status !== "undone" && `task-status-${status}`,
                    !isExecution && !task.dependencies?.length && "tree-task-leaf"
                  )}
                  style={{
                    left: pos.x,
                    top: pos.y,
                    width: pos.w,
                    height: pos.h,
                  }}
                  title={desc}
                  onClick={(e) => handleNodeClick(e, [task])}
                >
                  {desc}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {popover && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setPopover(null)}
            aria-hidden="true"
          />
          <div
            className="fixed z-50 bg-background border rounded-lg shadow-xl max-w-md p-4"
            style={{
              left: Math.min(popover.anchor.x + 8, typeof window !== "undefined" ? window.innerWidth - 320 : popover.anchor.x + 8),
              top: Math.min(
                popover.anchor.y - 100,
                typeof window !== "undefined" ? window.innerHeight - 250 : popover.anchor.y - 100
              ),
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
                {popover.tasks.map((t, i) => (
                  <TaskDetailBody
                    key={t.task_id}
                    task={t}
                    onRetry={handleRetry}
                    onResume={handleResume}
                  />
                ))}
              </div>
            )}
            <button
              type="button"
              className="absolute top-2 right-2 text-lg leading-none"
              onClick={() => setPopover(null)}
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </>
      )}
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
    <div className="space-y-2 text-sm">
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
      {isFailed && (
        <button
          type="button"
          className="rounded border px-2 py-1 text-xs hover:bg-muted"
          onClick={() => onRetry(task.task_id)}
        >
          Retry
        </button>
      )}
      {isUndone && (
        <button
          type="button"
          className="rounded border px-2 py-1 text-xs hover:bg-muted"
          onClick={() => onResume(task.task_id)}
        >
          Run from here
        </button>
      )}
    </div>
  )
}
