import { marked } from "marked"
import DOMPurify from "dompurify"

export function renderMarkdown(raw: string): string {
  if (!raw) return ""
  const html = marked.parse(raw, { async: false }) as string
  return DOMPurify.sanitize(html)
}

export function escapeHtml(s: string | null | undefined): string {
  if (s == null) return ""
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
}
