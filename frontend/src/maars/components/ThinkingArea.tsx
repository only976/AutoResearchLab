"use client"

import { useEffect, useRef, useState } from "react"
import { useMaars } from "../context/MaarsContext"
import { renderMarkdown, escapeHtml } from "../utils/markdown"
import { cn } from "@/lib/utils"

const TASK_BLOCK_HEIGHT = 192

export function ThinkingArea() {
  const { thinkingBlocks } = useMaars()
  const contentRef = useRef<HTMLDivElement>(null)
  const [focusedBlockKey, setFocusedBlockKey] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!contentRef.current) return
    const el = contentRef.current
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (nearBottom) {
      el.scrollTop = el.scrollHeight
    }
  }, [thinkingBlocks])

  useEffect(() => {
    if (!focusedBlockKey) return
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setFocusedBlockKey(null)
      }
    }
    document.addEventListener("click", handleClick)
    return () => document.removeEventListener("click", handleClick)
  }, [focusedBlockKey])

  if (thinkingBlocks.length === 0) {
    return (
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-muted/20">
        <div className="flex-1 overflow-auto p-4 text-sm text-muted-foreground">
          <p>Thinking will appear here when generating plan or executing tasks...</p>
        </div>
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className={cn(
        "flex-1 flex flex-col min-h-0 overflow-hidden bg-muted/20",
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
                className="rounded-md border border-dashed border-muted-foreground/30 bg-muted/30 px-3 py-2 text-muted-foreground shrink-0 transition-[background-color,border-color] duration-200 ease-out"
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
          const isFocused = focusedBlockKey === block.key
          return (
            <div
              key={block.key}
              className={cn(
                "rounded-md border border-border bg-background/50 overflow-hidden shrink-0 flex flex-col transition-[background-color,border-color,box-shadow] duration-200 ease-out",
                isFocused && "ring-2 ring-primary"
              )}
              style={{ height: TASK_BLOCK_HEIGHT }}
            >
              <div
                className="px-3 py-1.5 text-xs font-medium text-muted-foreground border-b bg-muted/30 shrink-0 cursor-pointer"
                onClick={() => setFocusedBlockKey(isFocused ? null : block.key)}
              >
                {escapeHtml(fullHeader)}
              </div>
              <div
                className={cn(
                  "flex-1 min-h-0 p-3 prose prose-sm dark:prose-invert max-w-none cursor-pointer",
                  isFocused ? "overflow-auto" : "overflow-hidden"
                )}
                onClick={() => setFocusedBlockKey(isFocused ? null : block.key)}
                dangerouslySetInnerHTML={{ __html: html }}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
