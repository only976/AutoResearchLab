"use client"

import { useMaars } from "../context/MaarsContext"
import type { MaarsView } from "../context/MaarsContext"
import { cn } from "@/lib/utils"

const TABS: { view: MaarsView; label: string }[] = [
  { view: "decomposition", label: "Decomposition" },
  { view: "execution", label: "Execution" },
  { view: "output", label: "Output" },
]

export function TreeViewTabs() {
  const { view, setView } = useMaars()

  return (
    <div className="flex gap-0.5 p-1 absolute top-1 left-1 z-20">
      {TABS.map(({ view: v, label }) => (
        <button
          key={v}
          type="button"
          onClick={() => setView(v)}
          className={cn(
            "px-2.5 py-1 text-xs font-medium rounded-md border border-border transition-[background-color,border-color,color] duration-200 ease-out",
            view === v
              ? "bg-background border-primary text-foreground"
              : "bg-muted/50 border-border text-muted-foreground hover:text-foreground hover:bg-muted"
          )}
          aria-pressed={view === v}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
