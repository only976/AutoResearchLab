import { NextResponse } from "next/server"
import path from "path"
import fs from "fs"

const CONFIG_FILENAME = "config.json"

function getConfigPath(): string {
  const candidates = [
    path.join(process.cwd(), "data", "db", CONFIG_FILENAME),
    path.join(process.cwd(), "..", "data", "db", CONFIG_FILENAME),
  ]
  for (const p of candidates) {
    if (fs.existsSync(p)) return p
  }
  return candidates[0]
}

const DEFAULT = {
  llm_model: "gemini-3-flash-preview",
  llm_api_base: "",
  llm_api_key: "",
  backend_port: 8010,
  frontend_port: 3030,
}

type ConfigRead = {
  llm_model: string
  llm_api_base: string | null
  llm_api_key: string
  llm_api_key_configured: boolean
  backend_port: number
  frontend_port: number
}

function readConfig(): ConfigRead {
  const configPath = getConfigPath()
  try {
    const raw = fs.readFileSync(configPath, "utf-8")
    const data = JSON.parse(raw) as Record<string, unknown>
    const apiKey = String(data?.llm_api_key ?? "").trim()
    const backendPort = Number(data?.backend_port ?? DEFAULT.backend_port) || DEFAULT.backend_port
    const frontendPort = Number(data?.frontend_port ?? DEFAULT.frontend_port) || DEFAULT.frontend_port
    return {
      llm_model: String(data?.llm_model ?? "").trim() || DEFAULT.llm_model,
      llm_api_base: (String(data?.llm_api_base ?? "").trim() || null) as string | null,
      llm_api_key: String(data?.llm_api_key ?? "").trim(),
      llm_api_key_configured: Boolean(apiKey),
      backend_port: backendPort,
      frontend_port: frontendPort,
    }
  } catch {
    return {
      llm_model: DEFAULT.llm_model,
      llm_api_base: null,
      llm_api_key: "",
      llm_api_key_configured: false,
      backend_port: DEFAULT.backend_port,
      frontend_port: DEFAULT.frontend_port,
    }
  }
}

function writeConfig(config: Record<string, unknown>): void {
  const configPath = getConfigPath()
  const dir = path.dirname(configPath)
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true })
  }
  const merged: Record<string, unknown> = { ...DEFAULT }
  const intKeys = new Set(["backend_port", "frontend_port"])
  for (const k of Object.keys(merged)) {
    const v = config[k]
    if (v !== undefined && v !== null) {
      if (intKeys.has(k)) {
        const n = Number(v)
        if (!Number.isNaN(n)) merged[k] = n
      } else {
        merged[k] = typeof v === "string" ? v : String(v)
      }
    }
  }
  fs.writeFileSync(configPath, JSON.stringify(merged, null, 2), "utf-8")
}

export async function GET() {
  const config = readConfig()
  return NextResponse.json(config)
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}))
  writeConfig(body as Record<string, unknown>)
  return NextResponse.json({ success: true })
}
