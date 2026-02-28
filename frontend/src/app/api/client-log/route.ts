import { promises as fs } from "fs"
import path from "path"

const MAX_MESSAGE = 2000

function resolveLogPath() {
  const baseDir = process.cwd()
  return path.resolve(baseDir, "..", "logs", "frontend.log")
}

export async function POST(request: Request) {
  const body = await request.text()
  const now = new Date().toISOString()
  const message = body.slice(0, MAX_MESSAGE).replace(/\s+/g, " ")
  const line = `${now} ${message}\n`

  const logPath = resolveLogPath()
  await fs.mkdir(path.dirname(logPath), { recursive: true })
  await fs.appendFile(logPath, line, "utf-8")

  return new Response("ok", { status: 200 })
}
