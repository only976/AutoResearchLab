"use client"

import { useEffect, useRef } from "react"
import { useMaars } from "../context/MaarsContext"
import { renderMarkdown, escapeHtml } from "../utils/markdown"
import { cn } from "@/lib/utils"

export function ThinkingArea() {
  const { thinkingBlocks } = useMaars()
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!contentRef.current) return
    const el = contentRef.current
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (nearBottom) {
      el.scrollTop = el.scrollHeight
    }
  }, [thinkingBlocks])

  if (thinkingBlocks.length === 0) {
    return (
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden rounded-lg border bg-muted/20">
        <div className="flex-1 overflow-auto p-4 text-sm text-muted-foreground">
          <p>Thinking will appear here when generating plan or executing tasks...</p>
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        "flex-1 flex flex-col min-h-0 overflow-hidden rounded-lg border bg-muted/20",
        "has-content"
      )}
    >
      <div
        ref={contentRef}
        className="flex-1 overflow-auto p-4 text-sm space-y-3 markdown-body"
      >
        {thinkingBlocks.map((block) => {
          if (block.blockType === "schedule") {
            const si = block.scheduleInfo || {}
            const parts: string[] = []
            if (si.turn != null) parts.push(`Turn ${si.turn}${si.max_turns != null ? `/${si.max_turns}` : ""}`)
            if (si.tool_name) parts.push(si.tool_name + (si.tool_args ? "(...)" : ""))
            const scheduleText = parts.length ? parts.join(" | ") : "Scheduling"
            return (
              <div
                key={block.key}
                className="rounded border border-dashed border-muted-foreground/30 bg-muted/30 px-3 py-2 text-muted-foreground"
              >
                {escapeHtml(scheduleText)}
              </div>
            )
          }
          const headerText =
            block.taskId != null
              ? `Task ${block.taskId} | ${block.operation || ""}`
              : block.operation || "Thinking"
          const si = block.scheduleInfo
          let fullHeader = headerText
          if (si) {
            const parts: string[] = []
            if (si.turn != null) parts.push(`Turn ${si.turn}${si.max_turns != null ? `/${si.max_turns}` : ""}`)
            if (si.tool_name) parts.push(si.tool_name + (si.tool_args ? "(...)" : ""))
            if (parts.length) fullHeader += " | " + parts.join(" | ")
          }
          const html = block.content ? renderMarkdown(block.content) : ""
          return (
            <div key={block.key} className="rounded border bg-background/50 overflow-hidden">
              <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground border-b bg-muted/30">
                {escapeHtml(fullHeader)}
              </div>
              <div
                className="p-3 prose prose-sm dark:prose-invert max-w-none"
                dangerouslySetInnerHTML={{ __html: html }}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
