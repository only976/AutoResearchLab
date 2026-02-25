"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import {
  LayoutDashboard,
  Lightbulb,
  FlaskConical,
  FileText,
  MessageSquare,
  ScrollText,
  Settings,
  Activity
} from "lucide-react"
import { useEffect, useState } from "react"

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/ideas", label: "Ideas", icon: Lightbulb },
  { href: "/experiments", label: "Experiments", icon: FlaskConical },
  { href: "/paper", label: "Paper Drafting", icon: FileText },
  { href: "/chat", label: "Chat Interface", icon: MessageSquare },
  { href: "/logs", label: "System Logs", icon: ScrollText },
  { href: "/config", label: "Configuration", icon: Settings },
]

export default function Sidebar() {
  const pathname = usePathname()
  const [backendStatus, setBackendStatus] = useState<boolean | null>(null)

  useEffect(() => {
    // Simple polling for backend status
    const checkStatus = async () => {
      try {
        const res = await fetch("/api/health")
        if (res.ok) setBackendStatus(true)
        else setBackendStatus(false)
      } catch {
        setBackendStatus(false)
      }
    }
    checkStatus()
    const interval = setInterval(checkStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <aside className="hidden h-screen w-64 flex-col border-r bg-card/50 backdrop-blur-xl px-4 py-6 md:flex fixed left-0 top-0 z-50">
      <div className="mb-8 px-2 flex items-center gap-2">
        <div className="h-8 w-8 rounded-lg bg-primary/20 flex items-center justify-center">
          <FlaskConical className="h-5 w-5 text-primary" />
        </div>
        <div>
          <div className="text-lg font-bold tracking-tight">AutoResearch</div>
          <div className="text-xs text-muted-foreground">Lab Automation</div>
        </div>
      </div>
      
      <nav className="flex flex-1 flex-col gap-1">
        {navItems.map((item) => {
          const isActive = pathname === item.href
          const Icon = item.icon
          
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all hover:bg-accent hover:text-accent-foreground",
                isActive 
                  ? "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90 hover:text-primary-foreground" 
                  : "text-muted-foreground"
              )}
            >
              <Icon className={cn("h-4 w-4", isActive ? "text-primary-foreground" : "text-muted-foreground group-hover:text-accent-foreground")} />
              {item.label}
            </Link>
          )
        })}
      </nav>

      <div className="mt-auto border-t pt-4">
        <div className="rounded-lg bg-muted/50 p-3 text-xs">
          <div className="flex items-center justify-between mb-2">
            <span className="font-medium text-muted-foreground">System Status</span>
            <Activity className="h-3 w-3 text-muted-foreground" />
          </div>
          <div className="flex items-center gap-2">
            <div className={cn("h-2 w-2 rounded-full", backendStatus ? "bg-green-500" : "bg-red-500 animate-pulse")} />
            <span className="text-muted-foreground">{backendStatus ? "Online" : "Offline"}</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
