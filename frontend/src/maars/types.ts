/**
 * MAARS types - aligned with backend API responses.
 */

export type TaskStatus =
  | "undone"
  | "doing"
  | "validating"
  | "done"
  | "validation-failed"
  | "execution-failed"

export interface TaskInput {
  description?: string
  format?: string
}

export interface TaskOutput {
  description?: string
  artifact?: string
  format?: string
}

export interface ValidationCriteria {
  description?: string
  criteria?: string[]
  optionalChecks?: string[]
}

export interface Task {
  task_id: string
  description?: string
  objective?: string
  dependencies?: string[]
  status?: TaskStatus
  input?: TaskInput
  output?: TaskOutput
  validation?: ValidationCriteria
  task_type?: string
  inputs?: unknown
  outputs?: unknown
  target?: string
  timeout_seconds?: number
}

export interface LayoutNode {
  x: number
  y: number
  w: number
  h: number
  ids?: string[]
}

export interface LayoutEdge {
  from: string | string[]
  to: string | string[]
  points?: [number, number][]
  adjacent?: boolean
}

export interface Layout {
  nodes: Record<string, LayoutNode>
  edges: LayoutEdge[]
  width: number
  height: number
  treeData?: Task[]
}

export interface Execution {
  tasks: Task[]
}

export interface ThinkingBlock {
  key: string
  blockType?: "schedule"
  taskId?: string | null
  operation?: string
  content?: string
  scheduleInfo?: {
    turn?: number
    max_turns?: number
    tool_name?: string
    tool_args?: unknown
  }
}

export type AiMode = "mock" | "llm" | "llmagent" | "agent"

export interface MaarsModeParam {
  key: string
  label: string
  type: "number" | "checkbox"
  min?: number
  max?: number
  step?: number
  default: number | boolean
  section: string
  tip?: string
}

export interface MaarsSettings {
  theme?: "light" | "dark" | "black"
  maxExecutionConcurrency?: number
  aiMode?: AiMode
  current?: string
  presets?: Record<string, MaarsPreset>
  modeConfig?: Record<AiMode, Record<string, number | boolean>>
  [key: string]: unknown
}

export interface MaarsPreset {
  label?: string
  baseUrl?: string
  apiKey?: string
  model?: string
  [key: string]: unknown
}
