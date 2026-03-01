"use client"

import { useMemo } from "react"
import { MaarsProvider, useMaars } from "@/maars/context/MaarsContext"
import {
  IdeaInputRow,
  TreeViewTabs,
  TaskTree,
  ThinkingArea,
  OutputArea,
} from "@/maars/components"
import { cn } from "@/lib/utils"

function ExperimentsContent() {
  const {
    view,
    treeData,
    layout,
    executionLayout,
    execution,
    taskStatusMap,
    qualityScore,
    qualityComment,
  } = useMaars()

  const decompositionTaskById = useMemo(() => {
    const m = new Map<string, import("@/maars/types").Task>()
    const flatten = (tasks: import("@/maars/types").Task[]) => {
      for (const t of tasks) {
        if (t?.task_id) m.set(t.task_id, t)
        const subs = (t as { subtasks?: import("@/maars/types").Task[] }).subtasks
        if (Array.isArray(subs)) flatten(subs)
      }
    }
    flatten(treeData)
    return m
  }, [treeData])

  const executionTaskById = useMemo(() => {
    const m = new Map<string, import("@/maars/types").Task>()
    const tasks = execution?.tasks || []
    tasks.forEach((t) => {
      if (t?.task_id) {
        const status = taskStatusMap[t.task_id] ?? t.status
        m.set(t.task_id, { ...t, status: status as import("@/maars/types").TaskStatus })
      }
    })
    return m
  }, [execution?.tasks, taskStatusMap])

  const execLayout = view === "execution" ? executionLayout : null
  const execTreeData = execution?.tasks || []
  const displayLayout = view === "execution" ? execLayout : layout
  const displayTreeData = view === "execution" ? execTreeData : treeData
  const displayTaskById = view === "execution" ? executionTaskById : decompositionTaskById

  return (
    <div className="w-full">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">MAARS</h1>
        <p className="text-muted-foreground text-sm">Multi-Agent Automated Research System</p>
      </header>

      <IdeaInputRow />

      <div className="flex h-[500px] border border-border rounded-none overflow-hidden bg-background">
        <div className="w-[30%] min-w-[200px] h-full flex flex-col shrink-0">
          <div className="relative flex-1 flex flex-col min-h-0 p-2">
            <TreeViewTabs />

            {view === "decomposition" && qualityScore != null && (
              <div
                className={cn(
                  "absolute bottom-8 right-3 z-20 text-xs px-2 py-1 rounded-md",
                  qualityScore >= 80 && "bg-green-500/20 text-green-700 dark:text-green-400",
                  qualityScore >= 60 && qualityScore < 80 && "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400",
                  qualityScore < 60 && "bg-red-500/20 text-red-700 dark:text-red-400"
                )}
                title={qualityComment || ""}
              >
                Quality: {qualityScore}
              </div>
            )}

            <div
              className={cn(
                "flex-1 flex flex-col min-h-0 overflow-hidden mt-10",
                view === "decomposition" && "flex",
                view === "execution" && "flex",
                view === "output" && "flex"
              )}
            >
              {view === "decomposition" && (
                <TaskTree
                  treeData={treeData}
                  layout={layout}
                  taskById={decompositionTaskById}
                  isExecution={false}
                />
              )}

              {view === "execution" && (
                <TaskTree
                  treeData={execTreeData}
                  layout={execLayout}
                  taskById={executionTaskById}
                  isExecution={true}
                />
              )}

              {view === "output" && <OutputArea />}
            </div>
          </div>
        </div>

        <div className="w-px shrink-0 bg-border" aria-hidden />
        <div className="flex-1 flex flex-col min-h-0 min-w-0 h-full">
          <ThinkingArea />
        </div>
      </div>
    </div>
  )
}

export default function ExperimentsPage() {
  return (
    <MaarsProvider>
      <ExperimentsContent />
    </MaarsProvider>
  )
}
