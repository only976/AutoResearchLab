"use client"

import { useState, useCallback, useEffect, useRef } from "react"
import { useMaars } from "../context/MaarsContext"
import { renderMarkdown, escapeHtml } from "../utils/markdown"
import { cn } from "@/lib/utils"

const TASK_BLOCK_HEIGHT = 192 // h-48 = 12rem = 192px

export function OutputArea() {
  const { taskOutputs } = useMaars()
  const [focusedTaskId, setFocusedTaskId] = useState<string | null>(null)
  const [modalTaskId, setModalTaskId] = useState<string | null>(null)
  const [modalContent, setModalContent] = useState<string>("")
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!focusedTaskId) return
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setFocusedTaskId(null)
      }
    }
    document.addEventListener("click", handleClick)
    return () => document.removeEventListener("click", handleClick)
  }, [focusedTaskId])

  const keys = Object.keys(taskOutputs).sort()

  const handleExpand = useCallback((taskId: string, contentHtml: string) => {
    setModalTaskId(taskId)
    setModalContent(contentHtml)
  }, [])

  const handleCloseModal = useCallback(() => {
    setModalTaskId(null)
    setModalContent("")
  }, [])

  const handleDownload = useCallback(
    (taskId: string) => {
      const raw = taskOutputs[taskId]
      let text = ""
      let ext = "txt"
      if (raw != null) {
        if (typeof raw === "string") {
          text = raw
          ext = "md"
        } else if (typeof raw === "object" && raw !== null && "content" in raw && typeof (raw as { content: unknown }).content === "string") {
          text = (raw as { content: string }).content
          ext = "md"
        } else {
          text = JSON.stringify(raw, null, 2)
          ext = "json"
        }
      }
      const filename = `task-${(taskId || "output").replace(/[^a-zA-Z0-9_-]/g, "_")}.${ext}`
      const blob = new Blob([text], { type: ext === "json" ? "application/json" : "text/markdown" })
      const a = document.createElement("a")
      a.href = URL.createObjectURL(blob)
      a.download = filename
      a.click()
      URL.revokeObjectURL(a.href)
    },
    [taskOutputs]
  )

  if (keys.length === 0) {
    return (
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <div className="flex-1 overflow-auto p-4 text-sm text-muted-foreground">
          <p>Task outputs will appear here after execution.</p>
        </div>
      </div>
    )
  }

  return (
    <>
      <div ref={containerRef} className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <div className="flex-1 overflow-auto p-4 space-y-3">
          {keys.map((taskId) => {
            const raw = taskOutputs[taskId]
            let content = ""
            if (typeof raw === "object") {
              content = renderMarkdown("```json\n" + JSON.stringify(raw, null, 2) + "\n```")
            } else {
              content = raw ? renderMarkdown(String(raw)) : ""
            }
            const isFocused = focusedTaskId === taskId
            return (
              <div
                key={taskId}
                className={cn(
                  "rounded-md border border-border overflow-hidden transition-[background-color,border-color,box-shadow] duration-200 ease-out shrink-0 flex flex-col",
                  isFocused && "ring-2 ring-primary"
                )}
                style={{ height: TASK_BLOCK_HEIGHT }}
              >
                <div
                  className="flex items-center justify-between px-3 py-2 border-b cursor-pointer shrink-0"
                  onClick={() => setFocusedTaskId(isFocused ? null : taskId)}
                >
                  <span className="text-sm font-medium">Task {escapeHtml(taskId)}</span>
                  <button
                    type="button"
                    className="text-xs text-muted-foreground hover:text-foreground"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleExpand(taskId, content)
                    }}
                    aria-label="Expand"
                  >
                    ⤢
                  </button>
                </div>
                <div
                  className={cn(
                    "flex-1 min-h-0 p-3 prose prose-sm dark:prose-invert max-w-none cursor-pointer",
                    isFocused ? "overflow-auto" : "overflow-hidden"
                  )}
                  onClick={() => setFocusedTaskId(isFocused ? null : taskId)}
                  dangerouslySetInnerHTML={{ __html: content }}
                />
              </div>
            )
          })}
        </div>
      </div>

      {modalTaskId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          role="dialog"
          aria-modal="true"
          aria-label="Task Output"
        >
          <div className="bg-background border border-border rounded-md shadow-xl max-w-4xl w-full max-h-[80vh] flex flex-col m-4">
            <div className="flex items-center justify-between px-4 py-2 border-b border-border">
              <span className="font-medium">Task {escapeHtml(modalTaskId)}</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="text-sm text-muted-foreground hover:text-foreground"
                  onClick={() => handleDownload(modalTaskId)}
                >
                  Download
                </button>
                <button
                  type="button"
                  className="text-lg leading-none"
                  onClick={handleCloseModal}
                  aria-label="Close"
                >
                  ×
                </button>
              </div>
            </div>
            <div
              className="flex-1 overflow-auto p-4 prose prose-sm dark:prose-invert max-w-none"
              dangerouslySetInnerHTML={{ __html: modalContent }}
            />
          </div>
        </div>
      )}
    </>
  )
}
