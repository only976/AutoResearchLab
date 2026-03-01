"use client"

import { useCallback, useEffect, useState } from "react"
import Section from "@/components/Section"
import { api, apiFetch } from "@/lib/api"

type ExperimentItem = {
  id: string
  title: string
  status: string
  updated_at?: number
}

type Conclusion = {
  summary?: string
  key_findings?: string[]
  recommendation?: string
}

type Plan = {
  experiment_name?: string
  steps?: Array<{ description?: string }>
}

type DraftResponse = {
  format: string
  content: string
}

type ArtifactManifestItem = {
  name: string
  type?: string
  stage?: string
  step_id?: string
  summary?: string | null
  for_next_stage?: boolean
  created_at?: string
}

export default function PaperPage() {
  const [experiments, setExperiments] = useState<ExperimentItem[]>([])
  const [selectedId, setSelectedId] = useState<string>("")
  const [plan, setPlan] = useState<Plan | null>(null)
  const [conclusion, setConclusion] = useState<Conclusion | null>(null)
  const [artifacts, setArtifacts] = useState<string[]>([])
  const [artifactManifest, setArtifactManifest] = useState<ArtifactManifestItem[]>([])
  const [draft, setDraft] = useState<DraftResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [title, setTitle] = useState("")
  const [abstractText, setAbstractText] = useState("")
  const [methodText, setMethodText] = useState("")
  const [resultsText, setResultsText] = useState("")
  const [discussion, setDiscussion] = useState("")

  const loadExperiments = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api<ExperimentItem[]>("experiments")
      setExperiments(data)
      if (!selectedId && data.length > 0) {
        setSelectedId(data[0].id)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  const loadDetails = async (expId: string) => {
    setLoading(true)
    setError(null)
    try {
      const [planRes, conclusionRes, artifactsRes] = await Promise.all([
        apiFetch(`experiments/${expId}/plan`),
        apiFetch(`experiments/${expId}/conclusion`),
        apiFetch(`experiments/${expId}/artifacts`)
      ])
      setPlan(planRes.ok ? await planRes.json() : null)
      setConclusion(conclusionRes.ok ? await conclusionRes.json() : null)
      const artifactsData = artifactsRes.ok ? await artifactsRes.json() : null
      const manifest = Array.isArray(artifactsData?.manifest) ? artifactsData.manifest : []
      setArtifactManifest(manifest)
      const nextStageFiles = manifest
        .filter((item: ArtifactManifestItem) => item.for_next_stage)
        .map((item: ArtifactManifestItem) => item.name)
      setArtifacts(nextStageFiles.length > 0 ? nextStageFiles : (artifactsData?.files || []))
      setDraft(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  const generateDraft = async (format: "markdown" | "latex") => {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    try {
      const data = await api<DraftResponse>(`experiments/${selectedId}/draft`, {
        method: "POST",
        body: { format }
      })
      setDraft(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (!draft) return
    const blob = new Blob([draft.content], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = draft.format === "latex" ? "paper.tex" : "paper.md"
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  useEffect(() => {
    loadExperiments()
  }, [loadExperiments])

  useEffect(() => {
    if (selectedId) {
      loadDetails(selectedId)
    }
  }, [selectedId])

  useEffect(() => {
    if (!plan && !conclusion) return
    const defaultTitle = plan?.experiment_name || "Untitled Research"
    const defaultAbstract = conclusion?.summary || "No summary available."
    const methodLines = plan?.steps?.map((step) => `- ${step.description || ""}`).join("\n") || ""
    const resultLines =
      conclusion?.key_findings?.map((finding) => `- ${finding}`).join("\n") || "No findings yet."
    setTitle(defaultTitle)
    setAbstractText(defaultAbstract)
    setMethodText(`The experiment followed these steps:\n${methodLines}`)
    setResultsText(`Key Findings:\n${resultLines}`)
    setDiscussion(conclusion?.recommendation || "")
  }, [plan, conclusion])

  return (
    <div className="flex flex-col gap-6">
      <Section title="Paper Drafting" description="Draft research papers from experiment outputs.">
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <select
              className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200"
              value={selectedId}
              onChange={(event) => setSelectedId(event.target.value)}
            >
              {experiments.map((exp) => (
                <option key={exp.id} value={exp.id}>
                  {exp.id}
                </option>
              ))}
            </select>
            <button
              className="rounded-xl border border-slate-700 px-4 py-2 text-xs text-slate-200 hover:border-slate-500"
              onClick={loadExperiments}
            >
              Refresh
            </button>
          </div>
          {loading ? <div className="text-xs text-slate-400">Loading...</div> : null}
          {error ? <div className="text-sm text-rose-400">{error}</div> : null}
          <div className="grid gap-3 md:grid-cols-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300">
              Status: {plan ? "Plan Ready" : "Missing Plan"}
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300">
              Conclusion: {conclusion ? "Available" : "Missing"}
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300">
              Artifacts: {artifacts.length} {artifactManifest.length > 0 ? `(manifest: ${artifactManifest.length})` : ""}
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300">
              Draft: {draft ? draft.format : "Not generated"}
            </div>
          </div>
        </div>
      </Section>

      <Section title="Draft Editor" description="Edit the core sections before exporting.">
        <div className="grid gap-4">
          <textarea
            className="min-h-[60px] rounded-2xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-100"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Title"
          />
          <textarea
            className="min-h-[120px] rounded-2xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-100"
            value={abstractText}
            onChange={(event) => setAbstractText(event.target.value)}
            placeholder="Abstract"
          />
          <textarea
            className="min-h-[160px] rounded-2xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-100"
            value={methodText}
            onChange={(event) => setMethodText(event.target.value)}
            placeholder="Methodology"
          />
          <textarea
            className="min-h-[160px] rounded-2xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-100"
            value={resultsText}
            onChange={(event) => setResultsText(event.target.value)}
            placeholder="Results"
          />
          <textarea
            className="min-h-[120px] rounded-2xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-100"
            value={discussion}
            onChange={(event) => setDiscussion(event.target.value)}
            placeholder="Discussion"
          />
        </div>
      </Section>

      <Section title="Figures & Data" description="Preview artifacts to include in the draft.">
        <div className="flex flex-wrap gap-2">
          {artifacts.length ? (
            artifacts.map((file) => {
              const item = artifactManifest.find((manifestItem) => manifestItem.name === file)
              const tag = item?.stage ? ` · ${item.stage}` : ""
              return (
                <a
                  key={file}
                  className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-200"
                  href={`/api/experiments/${selectedId}/artifacts/${file}`}
                  target="_blank"
                >
                  {file}{tag}
                </a>
              )
            })
          ) : (
            <div className="text-xs text-slate-400">No artifacts available</div>
          )}
        </div>
      </Section>

      <Section title="AI Full Draft" description="Generate a Markdown or LaTeX draft.">
        <div className="flex flex-wrap items-center gap-3">
          <button
            className="rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white hover:bg-accentSoft"
            onClick={() => generateDraft("markdown")}
          >
            Generate Markdown
          </button>
          <button
            className="rounded-xl border border-slate-700 px-4 py-2 text-xs text-slate-200 hover:border-slate-500"
            onClick={() => generateDraft("latex")}
          >
            Generate LaTeX
          </button>
          {draft ? (
            <button
              className="rounded-xl border border-slate-700 px-4 py-2 text-xs text-slate-200 hover:border-slate-500"
              onClick={handleDownload}
            >
              Download Draft
            </button>
          ) : null}
        </div>
        {draft ? (
          <pre className="mt-4 max-h-80 overflow-auto rounded-2xl border border-slate-800 bg-slate-950 p-4 text-xs text-slate-200">
            {draft.content}
          </pre>
        ) : (
          <div className="mt-4 text-xs text-slate-400">No draft generated yet</div>
        )}
      </Section>
    </div>
  )
}
