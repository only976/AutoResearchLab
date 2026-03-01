/**
 * MAARS API - backend API calls via /api/maars/*.
 */

import { api, apiFetch } from "@/lib/api"
import type {
  Execution,
  Layout,
  MaarsSettings,
  Task,
} from "./types"

const BASE = "maars"

async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json()
    return (data?.error as string) || fallback
  } catch {
    return fallback
  }
}

export async function fetchPlans(): Promise<{ planIds: string[] }> {
  const data = await api<{ planIds?: string[] }>(`${BASE}/plans`)
  return { planIds: data.planIds || [] }
}

export async function fetchPlan(planId: string): Promise<{ plan: { idea?: string; tasks?: Task[]; qualityScore?: number; qualityComment?: string } | null }> {
  return api(`${BASE}/plan?planId=${encodeURIComponent(planId)}`)
}

export async function fetchPlanTree(planId: string): Promise<{ treeData: Task[]; layout: Layout | null }> {
  const data = await api<{ treeData?: Task[]; layout?: Layout | null }>(
    `${BASE}/plan/tree?planId=${encodeURIComponent(planId)}`
  )
  return {
    treeData: data.treeData || [],
    layout: data.layout ?? null,
  }
}

export async function fetchPlanOutputs(planId: string): Promise<{ outputs: Record<string, unknown> }> {
  const data = await api<{ outputs?: Record<string, unknown> }>(
    `${BASE}/plan/outputs?planId=${encodeURIComponent(planId)}`
  )
  return { outputs: data.outputs || {} }
}

export async function runPlan(idea: string, signal?: AbortSignal): Promise<{ planId: string }> {
  const data = await api<{ planId?: string }>(`${BASE}/plan/run`, {
    method: "POST",
    body: { idea },
    signal,
  })
  if (!data.planId) throw new Error("No planId returned")
  return { planId: data.planId }
}

export async function stopPlan(): Promise<void> {
  await api(`${BASE}/plan/stop`, { method: "POST" })
}

export async function fetchExecution(planId: string): Promise<{ execution: Execution | null }> {
  const data = await api<{ execution?: Execution | null }>(
    `${BASE}/execution?planId=${encodeURIComponent(planId)}`
  )
  return { execution: data.execution ?? null }
}

export async function generateExecutionFromPlan(planId: string): Promise<{ execution: Execution }> {
  const data = await api<{ execution?: Execution }>(`${BASE}/execution/generate-from-plan`, {
    method: "POST",
    body: { planId },
  })
  if (!data.execution) throw new Error("No execution returned")
  return { execution: data.execution }
}

export async function fetchLayout(execution: Execution, planId: string): Promise<{ layout: Layout }> {
  const data = await api<{ layout?: Layout }>(`${BASE}/plan/layout`, {
    method: "POST",
    body: { execution, planId },
  })
  if (!data.layout) throw new Error("No layout returned")
  return { layout: data.layout }
}

export async function runExecution(planId: string, resumeFromTaskId?: string): Promise<void> {
  const res = await apiFetch(`${BASE}/execution/run`, {
    method: "POST",
    body: JSON.stringify(
      resumeFromTaskId ? { planId, resumeFromTaskId } : { planId }
    ),
    headers: { "Content-Type": "application/json" },
  })
  if (!res.ok) {
    const msg = await readErrorMessage(res, "Failed to start execution")
    throw new Error(msg)
  }
}

export async function stopExecution(): Promise<void> {
  await api(`${BASE}/execution/stop`, { method: "POST" })
}

export async function retryTask(planId: string, taskId: string): Promise<void> {
  const res = await apiFetch(`${BASE}/execution/retry-task`, {
    method: "POST",
    body: JSON.stringify({ planId, taskId }),
    headers: { "Content-Type": "application/json" },
  })
  if (!res.ok) {
    const msg = await readErrorMessage(res, "Failed to retry task")
    throw new Error(msg)
  }
}

export async function resumeFromTask(planId: string, taskId: string): Promise<void> {
  const res = await apiFetch(`${BASE}/execution/run`, {
    method: "POST",
    body: JSON.stringify({ planId, resumeFromTaskId: taskId }),
    headers: { "Content-Type": "application/json" },
  })
  if (!res.ok) {
    const msg = await readErrorMessage(res, "Failed to start execution")
    throw new Error(msg)
  }
}

export async function clearDb(): Promise<void> {
  await api(`${BASE}/db/clear`, { method: "POST" })
}

export async function fetchSettings(): Promise<MaarsSettings> {
  const data = await api<{ settings?: MaarsSettings }>(`${BASE}/settings`)
  return data.settings ?? {}
}

export async function saveSettings(settings: MaarsSettings): Promise<void> {
  await api(`${BASE}/settings`, {
    method: "POST",
    body: settings,
  })
}
