#!/usr/bin/env node
/**
 * Start backend or frontend using ports from config.json.
 * Usage: node scripts/start.js backend | node scripts/start.js frontend
 */
const { spawn } = require("child_process")
const path = require("path")
const fs = require("fs")

const configPath = path.join(__dirname, "..", "data", "db", "config.json")
let config = { backend_port: 8010, frontend_port: 3030 }
try {
  config = JSON.parse(fs.readFileSync(configPath, "utf-8"))
} catch {}

const cmd = process.argv[2]
if (cmd === "backend") {
  spawn("python", ["-m", "uvicorn", "backend.main:asgi_app", "--reload", "--port", String(config.backend_port || 8010)], {
    stdio: "inherit",
    shell: true,
    cwd: path.join(__dirname, ".."),
  })
} else if (cmd === "frontend") {
  spawn("npx", ["next", "dev", "--port", String(config.frontend_port || 3030)], {
    stdio: "inherit",
    shell: true,
    cwd: path.join(__dirname, "..", "frontend"),
  })
} else {
  console.error("Usage: node scripts/start.js backend | node scripts/start.js frontend")
  process.exit(1)
}
