"use client"

import { useState, useCallback } from "react"
import { useMaars } from "../context/MaarsContext"
import { renderMarkdown, escapeHtml } from "../utils/markdown"
import { cn } from "@/lib/utils"

export function OutputArea() {
  const { taskOutputs } = useMaars()
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null)
  const [modalTaskId, setModalTaskId] = useState<string | null>(null)
  const [modalContent, setModalContent] = useState<string>("")

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
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden rounded-lg border bg-muted/20">
        <div className="flex-1 overflow-auto p-4 text-sm text-muted-foreground">
          <p>Task outputs will appear here after execution.</p>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden rounded-lg border bg-muted/20">
        <div className="flex-1 overflow-auto p-4 space-y-3">
          {keys.map((taskId) => {
            const raw = taskOutputs[taskId]
            let content = ""
            if (typeof raw === "object") {
              content = renderMarkdown("```json\n" + JSON.stringify(raw, null, 2) + "\n```")
            } else {
              content = raw ? renderMarkdown(String(raw)) : ""
            }
            const isFocused = expandedTaskId === taskId
            return (
              <div
                key={taskId}
                className={cn(
                  "rounded border overflow-hidden transition-colors",
                  isFocused ? "ring-2 ring-primary" : "bg-background/50"
                )}
              >
                <div
                  className="flex items-center justify-between px-3 py-2 border-b bg-muted/30 cursor-pointer"
                  onClick={() => setExpandedTaskId(isFocused ? null : taskId)}
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
                  className="p-3 prose prose-sm dark:prose-invert max-w-none max-h-48 overflow-auto"
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
          <div className="bg-background border rounded-lg shadow-xl max-w-4xl w-full max-h-[80vh] flex flex-col m-4">
            <div className="flex items-center justify-between px-4 py-2 border-b">
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
