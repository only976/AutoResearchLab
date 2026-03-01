"use client"

import {
  createContext,
  useCallback,
  useContext,
  useReducer,
  type ReactNode,
} from "react"
import type { Execution, Layout, Task, ThinkingBlock } from "../types"

export type MaarsView = "decomposition" | "execution" | "output"

export interface MaarsState {
  planId: string | null
  idea: string
  treeData: Task[]
  layout: Layout | null
  executionLayout: Layout | null
  execution: Execution | null
  taskOutputs: Record<string, unknown>
  thinkingBlocks: ThinkingBlock[]
  planRunning: boolean
  executionRunning: boolean
  qualityScore: number | null
  qualityComment: string | null
  view: MaarsView
  previousTaskStates: Map<string, string>
  taskStatusMap: Record<string, string>
}

type MaarsAction =
  | { type: "SET_PLAN_ID"; planId: string | null }
  | { type: "SET_IDEA"; idea: string }
  | { type: "SET_TREE"; treeData: Task[]; layout: Layout | null }
  | { type: "SET_EXECUTION_LAYOUT"; layout: Layout | null }
  | { type: "SET_EXECUTION"; execution: Execution | null }
  | { type: "SET_TASK_OUTPUT"; taskId: string; output: unknown }
  | { type: "APPEND_THINKING"; block: ThinkingBlock }
  | { type: "APPEND_PLAN_CHUNK"; content: string; scheduleInfo?: ThinkingBlock["scheduleInfo"] }
  | { type: "UPDATE_THINKING"; key: string; content: string; scheduleInfo?: ThinkingBlock["scheduleInfo"] }
  | { type: "CLEAR_THINKING" }
  | { type: "SET_PLAN_RUNNING"; running: boolean }
  | { type: "SET_EXECUTION_RUNNING"; running: boolean }
  | { type: "SET_QUALITY"; score: number | null; comment: string | null }
  | { type: "SET_VIEW"; view: MaarsView }
  | { type: "TASK_STATE_UPDATE"; taskId: string; status: string }
  | { type: "TASK_STATES_BATCH"; updates: Array<{ taskId: string; status: string }> }
  | { type: "RESET" }

const initialState: MaarsState = {
  planId: null,
  idea: "",
  treeData: [],
  layout: null,
  executionLayout: null,
  execution: null,
  taskOutputs: {},
  thinkingBlocks: [],
  planRunning: false,
  executionRunning: false,
  qualityScore: null,
  qualityComment: null,
  view: "decomposition",
  previousTaskStates: new Map(),
  taskStatusMap: {},
}

function reducer(state: MaarsState, action: MaarsAction): MaarsState {
  switch (action.type) {
    case "SET_PLAN_ID":
      return { ...state, planId: action.planId }
    case "SET_IDEA":
      return { ...state, idea: action.idea }
    case "SET_TREE":
      return { ...state, treeData: action.treeData, layout: action.layout }
    case "SET_EXECUTION_LAYOUT":
      return { ...state, executionLayout: action.layout }
    case "SET_EXECUTION":
      return { ...state, execution: action.execution }
    case "SET_TASK_OUTPUT":
      return {
        ...state,
        taskOutputs: { ...state.taskOutputs, [action.taskId]: action.output },
      }
    case "APPEND_THINKING": {
      const blocks = [...state.thinkingBlocks, action.block]
      return { ...state, thinkingBlocks: blocks }
    }
    case "APPEND_PLAN_CHUNK": {
      const lastPlan = state.thinkingBlocks
        .slice()
        .reverse()
        .find((b) => !b.blockType && b.taskId == null)
      if (lastPlan) {
        const blocks = state.thinkingBlocks.map((b) =>
          b.key === lastPlan.key
            ? { ...b, content: (b.content || "") + action.content, scheduleInfo: action.scheduleInfo ?? b.scheduleInfo }
            : b
        )
        return { ...state, thinkingBlocks: blocks }
      }
      const newBlock: ThinkingBlock = {
        key: `plan_${Date.now()}`,
        taskId: null,
        operation: "Plan",
        content: action.content,
        scheduleInfo: action.scheduleInfo ?? undefined,
      }
      return { ...state, thinkingBlocks: [...state.thinkingBlocks, newBlock] }
    }
    case "UPDATE_THINKING": {
      const existing = state.thinkingBlocks.find((b) => b.key === action.key)
      if (existing) {
        const blocks = state.thinkingBlocks.map((b) =>
          b.key === action.key
            ? { ...b, content: (b.content || "") + action.content, scheduleInfo: action.scheduleInfo ?? b.scheduleInfo }
            : b
        )
        return { ...state, thinkingBlocks: blocks }
      }
      const [taskId, operation] = action.key.includes("::") ? action.key.split("::") : [null, ""]
      const newBlock: ThinkingBlock = {
        key: action.key,
        taskId: taskId || undefined,
        operation: operation || "",
        content: action.content,
        scheduleInfo: action.scheduleInfo ?? undefined,
      }
      return { ...state, thinkingBlocks: [...state.thinkingBlocks, newBlock] }
    }
    case "CLEAR_THINKING":
      return {
        ...state,
        thinkingBlocks: [],
        taskOutputs: {},
      }
    case "SET_PLAN_RUNNING":
      return { ...state, planRunning: action.running }
    case "SET_EXECUTION_RUNNING":
      return { ...state, executionRunning: action.running }
    case "SET_QUALITY":
      return { ...state, qualityScore: action.score, qualityComment: action.comment }
    case "SET_VIEW":
      return { ...state, view: action.view }
    case "TASK_STATE_UPDATE": {
      const prev = new Map(state.previousTaskStates)
      prev.set(action.taskId, action.status)
      const statusMap = { ...state.taskStatusMap, [action.taskId]: action.status }
      return { ...state, previousTaskStates: prev, taskStatusMap: statusMap }
    }
    case "TASK_STATES_BATCH": {
      const statusMap = { ...state.taskStatusMap }
      action.updates.forEach(({ taskId, status }) => {
        statusMap[taskId] = status
      })
      const prev = new Map(state.previousTaskStates)
      action.updates.forEach(({ taskId, status }) => prev.set(taskId, status))
      return { ...state, previousTaskStates: prev, taskStatusMap: statusMap }
    }
    case "RESET":
      return {
        ...initialState,
        planId: state.planId,
        idea: state.idea,
      }
    default:
      return state
  }
}

interface MaarsContextValue extends MaarsState {
  dispatch: React.Dispatch<MaarsAction>
  setPlanId: (id: string | null) => void
  setIdea: (idea: string) => void
  setView: (view: MaarsView) => void
}

const MaarsContext = createContext<MaarsContextValue | null>(null)

export function MaarsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)

  const setPlanId = useCallback((planId: string | null) => {
    dispatch({ type: "SET_PLAN_ID", planId })
  }, [])

  const setIdea = useCallback((idea: string) => {
    dispatch({ type: "SET_IDEA", idea })
  }, [])

  const setView = useCallback((view: MaarsView) => {
    dispatch({ type: "SET_VIEW", view })
  }, [])

  const value: MaarsContextValue = {
    ...state,
    dispatch,
    setPlanId,
    setIdea,
    setView,
  }

  return (
    <MaarsContext.Provider value={value}>
      {children}
    </MaarsContext.Provider>
  )
}

export function useMaars() {
  const ctx = useContext(MaarsContext)
  if (!ctx) throw new Error("useMaars must be used within MaarsProvider")
  return ctx
}
