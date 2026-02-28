import { getApiBaseUrl } from "./config"

export const API_BASE_URL = process.env.API_BASE_URL || getApiBaseUrl()

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}
