"use client"

import { useEffect, useState, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
  Palette,
  Database,
  Cpu,
  RefreshCw,
  Trash2,
  Plus,
  ChevronDown,
  ChevronRight,
  Key,
  Server,
  Box,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card"
import { Button } from "@/components/ui/Button"
import { Input } from "@/components/ui/Input"
import { fetchSettings, saveSettings, clearDb } from "@/maars/api"
import type { MaarsSettings, MaarsPreset, AiMode } from "@/maars/types"

const THEMES = ["light", "dark", "black"] as const
const AI_MODES: AiMode[] = ["mock", "llm", "llmagent", "agent"]

const MODE_DESCRIPTIONS: Record<AiMode, { title: string; desc: string }> = {
  mock: {
    title: "Mock",
    desc: "Use mock data, no API key required.",
  },
  llm: {
    title: "LLM",
    desc: "Plan and task execution both use LLM (single-turn).",
  },
  llmagent: {
    title: "LLM+Agent",
    desc: "Plan uses LLM; task execution uses Agent mode with tools.",
  },
  agent: {
    title: "Agent",
    desc: "Plan and task execution both use Agent mode (ReAct-style).",
  },
}

const MODE_PARAMS: Record<AiMode, Array<{ key: string; label: string; type: "number" | "checkbox"; min?: number; max?: number; step?: number; default: number | boolean; section: string; tip?: string }>> = {
  mock: [
    { key: "executionPassProbability", label: "Execution pass rate", type: "number", min: 0, max: 1, step: 0.05, default: 0.95, section: "Mock", tip: "Random pass probability for mock execution" },
    { key: "validationPassProbability", label: "Validation pass rate", type: "number", min: 0, max: 1, step: 0.05, default: 0.95, section: "Mock", tip: "Random pass probability for mock validation" },
    { key: "maxFailures", label: "Max retries", type: "number", min: 1, max: 10, default: 3, section: "Mock", tip: "Max retries after task failure" },
  ],
  llm: [
    { key: "planLlmTemperature", label: "Plan Temperature", type: "number", min: 0, max: 2, step: 0.1, default: 0.3, section: "Plan", tip: "Temperature for plan LLM calls" },
    { key: "taskLlmTemperature", label: "Task Temperature", type: "number", min: 0, max: 2, step: 0.1, default: 0.3, section: "Task", tip: "Temperature for task execution LLM" },
    { key: "maxFailures", label: "Max retries", type: "number", min: 1, max: 10, default: 3, section: "Task", tip: "Max retries after failure" },
  ],
  llmagent: [
    { key: "planLlmTemperature", label: "Plan Temperature", type: "number", min: 0, max: 2, step: 0.1, default: 0.3, section: "Plan", tip: "Temperature for plan LLM" },
    { key: "taskLlmTemperature", label: "Task Temperature", type: "number", min: 0, max: 2, step: 0.1, default: 0.3, section: "Task Agent", tip: "Temperature for task Agent LLM" },
    { key: "taskAgentMaxTurns", label: "Task max turns", type: "number", min: 1, max: 30, default: 15, section: "Task Agent", tip: "Max turns for task Agent loop" },
    { key: "maxFailures", label: "Max retries", type: "number", min: 1, max: 10, default: 3, section: "Task Agent", tip: "Max retries after failure" },
  ],
  agent: [
    { key: "planAgentMaxTurns", label: "Plan max turns", type: "number", min: 1, max: 50, default: 30, section: "Plan Agent", tip: "Max turns for plan Agent loop" },
    { key: "planLlmTemperature", label: "Plan Temperature", type: "number", min: 0, max: 2, step: 0.1, default: 0.3, section: "Plan Agent", tip: "Temperature for plan Agent LLM" },
    { key: "taskLlmTemperature", label: "Task Temperature", type: "number", min: 0, max: 2, step: 0.1, default: 0.3, section: "Task Agent", tip: "Temperature for task Agent LLM" },
    { key: "taskAgentMaxTurns", label: "Task max turns", type: "number", min: 1, max: 30, default: 15, section: "Task Agent", tip: "Max turns for task Agent loop" },
    { key: "maxFailures", label: "Max retries", type: "number", min: 1, max: 10, default: 3, section: "Task Agent", tip: "Max retries after failure" },
  ],
}

function generatePresetKey(label: string, existing: Record<string, MaarsPreset>): string {
  const base = (label || "preset").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "preset"
  let key = base
  let i = 2
  while (existing[key]) {
    key = `${base}_${i++}`
  }
  return key
}

export function MaarsSettingsSection() {
  const [settings, setSettings] = useState<MaarsSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [modeConfigExpanded, setModeConfigExpanded] = useState(false)

  const loadSettings = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchSettings()
      setSettings(data)
      setError(null)
      if (!data.presets || Object.keys(data.presets).length === 0) {
        setSettings((prev) =>
          prev
            ? {
                ...prev,
                presets: { default: { label: "Default", baseUrl: "", apiKey: "", model: "" } },
                current: "default",
              }
            : null
        )
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load MAARS settings")
    } finally {
      setLoading(false)
    }
  }, [])

  const saveMaarsSettings = async () => {
    if (!settings) return
    setSaving(true)
    setError(null)
    try {
      await saveSettings(settings)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save")
    } finally {
      setSaving(false)
    }
  }

  const handleClearDb = async () => {
    if (!confirm("Clear all MAARS plans and execution data? This cannot be undone.")) return
    try {
      await clearDb()
      alert("Database cleared.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear DB")
    }
  }

  const updateField = (key: keyof MaarsSettings, value: unknown) => {
    setSettings((prev) => (prev ? { ...prev, [key]: value } : null))
  }

  const updatePreset = (presetKey: string, field: keyof MaarsPreset, value: string) => {
    setSettings((prev) => {
      if (!prev) return null
      const presets = { ...(prev.presets || {}) }
      presets[presetKey] = { ...(presets[presetKey] || {}), [field]: value }
      return { ...prev, presets }
    })
  }

  const addPreset = () => {
    const presets = settings?.presets || {}
    const key = generatePresetKey("new", presets)
    setSettings((prev) => ({
      ...prev!,
      presets: { ...presets, [key]: { label: "New Preset", baseUrl: "", apiKey: "", model: "" } },
      current: key,
    }))
  }

  const deletePreset = (key: string) => {
    const presets = settings?.presets || {}
    if (Object.keys(presets).length <= 1) return
    const next = { ...presets }
    delete next[key]
    const remaining = Object.keys(next)
    setSettings((prev) => ({
      ...prev!,
      presets: next,
      current: prev?.current === key ? remaining[0] : prev?.current,
    }))
  }

  const updateModeConfig = (mode: AiMode, paramKey: string, value: number | boolean) => {
    setSettings((prev) => {
      if (!prev) return null
      const modeConfig: Record<string, Record<string, number | boolean>> = { ...(prev.modeConfig || {}) }
      const modeCfg = { ...(modeConfig[mode] || {}) }
      modeCfg[paramKey] = value
      modeConfig[mode] = modeCfg
      return { ...prev, modeConfig }
    })
  }

  const getModeConfigValue = (mode: AiMode, paramKey: string, defaultVal: number | boolean): number | boolean => {
    const modeCfg = settings?.modeConfig?.[mode]
    if (modeCfg && paramKey in modeCfg) return modeCfg[paramKey] as number | boolean
    return defaultVal
  }

  useEffect(() => {
    loadSettings()
  }, [loadSettings])

  useEffect(() => {
    if (settings?.theme) {
      const root = document.documentElement
      if (settings.theme === "light") {
        root.removeAttribute("data-theme")
      } else {
        root.setAttribute("data-theme", settings.theme)
      }
    }
  }, [settings?.theme])

  if (loading) {
    return (
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin" />
            Loading MAARS settings...
          </div>
        </CardContent>
      </Card>
    )
  }

  const item = { hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }
  const presets = settings?.presets || {}
  const presetKeys = Object.keys(presets)
  const currentPreset = settings?.current && presets[settings.current] ? presets[settings.current] : null
  const aiMode = settings?.aiMode || "mock"
  const modeParams = MODE_PARAMS[aiMode] || []

  return (
    <motion.div variants={{ show: { transition: { staggerChildren: 0.05 } } }} initial="hidden" animate="show">
      <h2 className="text-lg font-semibold mb-4">MAARS Settings</h2>
      {error && (
        <div className="mb-4 p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive">
          {error}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <motion.div variants={item}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Theme</CardTitle>
              <Palette className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="flex gap-2">
                {THEMES.map((t) => (
                  <Button
                    key={t}
                    variant={settings?.theme === t ? "default" : "outline"}
                    size="sm"
                    onClick={() => updateField("theme", t)}
                  >
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div variants={item}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">AI Mode</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {AI_MODES.map((m) => (
                  <Button
                    key={m}
                    variant={settings?.aiMode === m ? "default" : "outline"}
                    size="sm"
                    onClick={() => updateField("aiMode", m)}
                  >
                    {m}
                  </Button>
                ))}
              </div>
              <p className="text-xs text-muted-foreground mt-2">{MODE_DESCRIPTIONS[aiMode].desc}</p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div variants={item}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Max Concurrent Tasks</CardTitle>
              <Cpu className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <Input
                type="number"
                min={1}
                max={32}
                value={settings?.maxExecutionConcurrency ?? 7}
                onChange={(e) => updateField("maxExecutionConcurrency", parseInt(e.target.value, 10) || 7)}
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground mt-2">Maximum tasks running in parallel during execution</p>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Presets */}
      <motion.div variants={item} className="mt-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">API Presets</CardTitle>
            <Button variant="outline" size="sm" onClick={addPreset}>
              <Plus className="mr-2 h-4 w-4" />
              Add
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {presetKeys.map((key) => (
                <Button
                  key={key}
                  variant={settings?.current === key ? "default" : "outline"}
                  size="sm"
                  onClick={() => updateField("current", key)}
                >
                  {presets[key]?.label || key}
                </Button>
              ))}
            </div>
            {currentPreset && (
              <div className="space-y-3 pt-2 border-t">
                <p className="text-xs text-muted-foreground">Current preset: {settings?.current}</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="text-xs text-muted-foreground">Label</label>
                    <Input
                      value={currentPreset.label || ""}
                      onChange={(e) => settings?.current && updatePreset(settings.current, "label", e.target.value)}
                      placeholder="Preset name"
                      className="mt-1"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground flex items-center gap-1">
                      <Key className="h-3 w-3" /> API Key
                    </label>
                    <Input
                      type="password"
                      value={currentPreset.apiKey || ""}
                      onChange={(e) => settings?.current && updatePreset(settings.current, "apiKey", e.target.value)}
                      placeholder="API key"
                      className="mt-1 font-mono"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground flex items-center gap-1">
                      <Box className="h-3 w-3" /> Model
                    </label>
                    <Input
                      value={currentPreset.model || ""}
                      onChange={(e) => settings?.current && updatePreset(settings.current, "model", e.target.value)}
                      placeholder="e.g. gemini-3-flash-preview"
                      className="mt-1 font-mono"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground flex items-center gap-1">
                      <Server className="h-3 w-3" /> Base URL
                    </label>
                    <Input
                      value={currentPreset.baseUrl || ""}
                      onChange={(e) => settings?.current && updatePreset(settings.current, "baseUrl", e.target.value)}
                      placeholder="Leave empty for native"
                      className="mt-1 font-mono"
                    />
                  </div>
                </div>
                {presetKeys.length > 1 && (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => settings?.current && deletePreset(settings.current)}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete this preset
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Mode Config */}
      {modeParams.length > 0 && (
        <motion.div variants={item} className="mt-6">
          <Card>
            <CardHeader
              className="cursor-pointer select-none"
              onClick={() => setModeConfigExpanded((x) => !x)}
            >
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  {modeConfigExpanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                  Mode Config ({MODE_DESCRIPTIONS[aiMode].title})
                </CardTitle>
              </div>
            </CardHeader>
            <AnimatePresence>
              {modeConfigExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <CardContent className="pt-0 space-y-4">
                    {Object.entries(
                      modeParams.reduce<Record<string, typeof modeParams>>((acc, p) => {
                        (acc[p.section] = acc[p.section] || []).push(p)
                        return acc
                      }, {})
                    ).map(([section, params]) => (
                      <div key={section}>
                        <h4 className="text-xs font-medium text-muted-foreground mb-2">{section}</h4>
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                          {params.map((param) => (
                            <div key={param.key} title={param.tip}>
                              <label className="text-xs text-muted-foreground">{param.label}</label>
                              {param.type === "checkbox" ? (
                                <div className="mt-1">
                                  <input
                                    type="checkbox"
                                    checked={
                                      getModeConfigValue(aiMode, param.key, param.default) === true
                                    }
                                    onChange={(e) =>
                                      updateModeConfig(aiMode, param.key, e.target.checked)
                                    }
                                    className="rounded border-input"
                                  />
                                </div>
                              ) : (
                                <Input
                                  type="number"
                                  min={param.min}
                                  max={param.max}
                                  step={param.step}
                                  value={String(
                                    getModeConfigValue(aiMode, param.key, param.default) as number
                                  )}
                                  onChange={(e) => {
                                    const v = parseFloat(e.target.value)
                                    updateModeConfig(aiMode, param.key, isNaN(v) ? (param.default as number) : v)
                                  }}
                                  className="mt-1 font-mono"
                                />
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </motion.div>
              )}
            </AnimatePresence>
          </Card>
        </motion.div>
      )}

      {/* DB */}
      <motion.div variants={item} className="mt-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">DB Operation</CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={loadSettings}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Refresh
              </Button>
              <Button variant="destructive" size="sm" onClick={handleClearDb}>
                <Trash2 className="mr-2 h-4 w-4" />
                Clear DB
              </Button>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <div className="mt-4">
        <Button onClick={saveMaarsSettings} disabled={saving || !settings}>
          {saving ? "Saving..." : "Save MAARS Settings"}
        </Button>
      </div>
    </motion.div>
  )
}
