/** Thin fetch wrapper: same-origin session cookie + CSRF header, JSON in/out, typed errors. */

export class ApiError extends Error {
  status: number
  data: unknown
  constructor(status: number, message: string, data: unknown) {
    super(message)
    this.status = status
    this.data = data
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.split('; ').find((c) => c.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.split('=')[1]) : null
}

let csrfReady: Promise<void> | null = null

export async function ensureCsrf(force = false): Promise<void> {
  if (force || !readCookie('csrftoken')) csrfReady = null
  csrfReady ??= fetch('/api/auth/csrf/', { credentials: 'same-origin' }).then(() => undefined)
  return csrfReady
}

/** Turns a DRF error body into one readable sentence. */
export function errorMessage(data: unknown, fallback = 'Something went wrong.'): string {
  if (!data || typeof data !== 'object') return fallback
  const d = data as Record<string, unknown>
  if (typeof d.detail === 'string') return d.detail
  for (const value of Object.values(d)) {
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
    if (typeof value === 'string') return value
  }
  return fallback
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (init.json !== undefined) headers.set('Content-Type', 'application/json')
  if (method !== 'GET' && method !== 'HEAD') {
    await ensureCsrf()
    headers.set('X-CSRFToken', readCookie('csrftoken') ?? '')
  }
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      method,
      headers,
      credentials: 'same-origin',
      body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
    })
  } catch {
    throw new ApiError(0, 'Network error. Check your connection and try again.', null)
  }
  if (response.status === 204) return undefined as T
  const text = await response.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (!response.ok) throw new ApiError(response.status, errorMessage(data, `Request failed (${response.status}).`), data)
  return data as T
}

export type SSEEvent = { event: string; data: Record<string, unknown> }

/** Parses complete SSE blocks out of a text buffer; returns parsed events and the unconsumed remainder. */
export function parseSSE(buffer: string): { events: SSEEvent[]; rest: string } {
  const events: SSEEvent[] = []
  const blocks = buffer.split('\n\n')
  const rest = blocks.pop() ?? ''
  for (const block of blocks) {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) event = line.slice(7)
      else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
    }
    if (!dataLines.length) continue
    try {
      events.push({ event, data: JSON.parse(dataLines.join('\n')) })
    } catch {
      // ignore malformed block
    }
  }
  return { events, rest }
}

/**
 * POSTs JSON and consumes a text/event-stream response, calling onEvent for each event.
 * Non-streaming error responses (400/403/404/429) are thrown as ApiError.
 */
export async function postStream(
  path: string,
  body: unknown,
  onEvent: (e: SSEEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  await ensureCsrf()
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': readCookie('csrftoken') ?? '' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok || !response.body) {
    let data: unknown = null
    try {
      data = await response.json()
    } catch {
      data = null
    }
    throw new ApiError(response.status, errorMessage(data, `Request failed (${response.status}).`), data)
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    const parsed = parseSSE(buffer)
    buffer = parsed.rest
    parsed.events.forEach(onEvent)
  }
}
