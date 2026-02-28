type LogLevel = "info" | "warn" | "error"

export async function logClientEvent(level: LogLevel, message: string, meta?: Record<string, unknown>) {
  const payload = {
    level,
    message,
    meta: meta || {}
  }
  try {
    await fetch("/api/client-log", {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: JSON.stringify(payload)
    })
  } catch {
    // Best-effort logging only.
  }
}
