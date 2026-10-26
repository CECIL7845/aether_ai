export type User = { id: number; email: string; display_name: string; date_joined: string }

export type MessageStatus = 'complete' | 'streaming' | 'stopped' | 'error'

export type Message = {
  id: number
  role: 'user' | 'assistant'
  content: string
  status: MessageStatus
  error_kind: string
  error_message: string
  model_id: string
  stop_reason: string
  input_tokens: number | null
  output_tokens: number | null
  cost_usd: string | null
  citations: SourceRef[]
  invalid_citations: string[]
  created_at: string
  tool_calls?: ToolCall[]
  artifacts?: Artifact[]
  first_token_ms?: number | null
  duration_ms?: number | null
  /** Client-only: what the server reported about document grounding while streaming this reply. */
  grounding?: GroundingInfo
  /** Client-only: current server stage while waiting for the first words. */
  stage?: { stage: 'searching_web' | 'reading_documents' | 'generating'; provider?: string; since: number }
}

export type SourceRef = {
  ref: string
  kind: 'document' | 'web'
  document_id: number | null
  url: string
  title: string
  location: string
  retrieved: boolean
  snippet: string
}

export type WebPage = { ref?: string; url: string; title: string; status: 'read' | 'snippet' | 'failed'; reason?: string }

export type GroundingInfo = {
  mode?: 'full' | 'search' | 'none'
  sources?: SourceRef[]
  skipped?: { title: string; status: DocumentStatus }[]
  web?: { query?: string; pages: WebPage[]; sources: SourceRef[]; error?: string }
}

export type DocumentStatus = 'queued' | 'processing' | 'ready' | 'failed'

export type DocumentInfo = {
  id: number
  title: string
  kind: 'pdf' | 'docx' | 'text' | 'csv' | 'xlsx'
  size: number
  status: DocumentStatus
  error: string
  page_count: number | null
  char_count: number
  chunk_count: number
  embedding_model: string
  created_at: string
  updated_at: string
}

export type AttachedDocument = Pick<DocumentInfo, 'id' | 'title' | 'kind' | 'status' | 'error'>

export type Conversation = {
  id: number
  title: string
  model_id: string
  archived: boolean
  document_ids: number[]
  documents: AttachedDocument[]
  created_at: string
  updated_at: string
}

export type ConversationDetail = Conversation & { messages: Message[] }

export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] }

export type ModelInfo = {
  id: string
  provider: string
  label: string
  context_window: number
  max_output_tokens: number
  supports_vision: boolean
  supports_tools: boolean
  input_price_per_mtok: string | null
  output_price_per_mtok: string | null
  available: boolean
}

export type ModelsResponse = { default: string | null; models: ModelInfo[]; features: { web_search: boolean } }

export type UsageResponse = {
  allowed: boolean
  reason: string
  tokens_last_24h: number
  daily_token_limit: number
  cost_this_month_usd: string
  monthly_cost_limit_usd: string
}

export type ToolCall = {
  id: string
  name: string
  args: Record<string, unknown>
  status: 'running' | 'done' | 'error'
  summary: string
}

export type TableArtifact = {
  type: 'table'
  result_id: number
  title: string
  columns: string[]
  rows: (string | number | boolean | null)[][]
  total_rows: number
}

export type ChartArtifact = {
  type: 'chart'
  chart_type: 'bar' | 'line' | 'scatter'
  title: string
  x: string
  y: string[]
  points: number
  truncated: boolean
  data: Record<string, string | number | null>[]
}

export type Artifact = TableArtifact | ChartArtifact
