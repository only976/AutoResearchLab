/**
 * Read backend API base URL from config.json. Used by API routes to proxy to backend.
 */
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

export function getApiBaseUrl(): string {
  try {
    const configPath = getConfigPath()
    const raw = fs.readFileSync(configPath, "utf-8")
    const data = JSON.parse(raw) as Record<string, unknown>
    const port = Number(data?.backend_port ?? 8010)
    return `http://localhost:${port}`
  } catch {
    return "http://localhost:8010"
  }
}

export function getFrontendPort(): number {
  try {
    const configPath = getConfigPath()
    const raw = fs.readFileSync(configPath, "utf-8")
    const data = JSON.parse(raw) as Record<string, unknown>
    return Number(data?.frontend_port ?? 3030)
  } catch {
    return 3030
  }
}
