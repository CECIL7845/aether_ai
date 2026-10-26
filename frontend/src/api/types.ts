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
  /** Client-only: what the server reported about document grounding while streaming this reply. */
  grounding?: GroundingInfo
}

export type SourceRef = { ref: string; document_id: number; title: string; location: string; snippet: string }

export type GroundingInfo = {
  mode: 'full' | 'search' | 'none'
  sources: SourceRef[]
  skipped: { title: string; status: DocumentStatus }[]
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

export type ModelsResponse = { default: string | null; models: ModelInfo[] }

export type UsageResponse = {
  allowed: boolean
  reason: string
  tokens_last_24h: number
  daily_token_limit: number
  cost_this_month_usd: string
  monthly_cost_limit_usd: string
}
