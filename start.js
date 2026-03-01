#!/usr/bin/env node
/**
 * Start backend and/or frontend using ports from config.json.
 * Usage:
 *   node start.js          # 同时启动后端 + 前端（一行命令）
 *   node start.js backend  # 仅后端
 *   node start.js frontend # 仅前端
 */
const { spawn } = require("child_process")
const path = require("path")
const fs = require("fs")

const rootDir = __dirname
const configPath = path.join(rootDir, "backend", "db", "config.json")
let config = { frontend_port: 3030 }
try {
  config = JSON.parse(fs.readFileSync(configPath, "utf-8"))
} catch {}

const BACKEND_PORT = 8888
const FRONTEND_PORT = config?.frontend_port ?? 3030
const frontendDir = path.join(rootDir, "frontend")

const children = []

function spawnBackend() {
  const child = spawn("python", ["-m", "uvicorn", "backend.main:asgi_app", "--reload", "--port", String(BACKEND_PORT)], {
    stdio: "inherit",
    shell: true,
    cwd: rootDir,
  })
  children.push(child)
  return child
}

function spawnFrontend() {
  const child = spawn("npx", ["next", "dev", "--port", String(FRONTEND_PORT)], {
    stdio: "inherit",
    shell: true,
    cwd: frontendDir,
  })
  children.push(child)
  return child
}

function killAll() {
  children.forEach((c) => {
    try {
      c.kill("SIGTERM")
    } catch {}
  })
  process.exit()
}

process.on("SIGINT", killAll)
process.on("SIGTERM", killAll)

const cmd = process.argv[2]
if (cmd === "backend") {
  spawnBackend()
} else if (cmd === "frontend") {
  spawnFrontend()
} else if (!cmd || cmd === "all") {
  console.log("Starting backend (port %d) and frontend (port %d)...", BACKEND_PORT, FRONTEND_PORT)
  spawnBackend()
  spawnFrontend()
} else {
  console.error("Usage: node start.js [backend|frontend]")
  console.error("  (no args)  - start both backend and frontend")
  process.exit(1)
}
