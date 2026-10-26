import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, postStream, type SSEEvent } from '../api/client'
import { conversations } from '../api/endpoints'
import type { Artifact, ConversationDetail, GroundingInfo, Message, SourceRef, ToolCall } from '../api/types'

let tempId = -1
const nextTempId = () => tempId--

function draft(role: Message['role'], content: string, status: Message['status'] = 'complete'): Message {
  return {
    id: nextTempId(),
    role,
    content,
    status,
    error_kind: '',
    error_message: '',
    model_id: '',
    stop_reason: '',
    input_tokens: null,
    output_tokens: null,
    cost_usd: null,
    citations: [],
    invalid_citations: [],
    created_at: new Date().toISOString(),
  }
}

type Options = {
  onTitle?: (id: number, title: string) => void
  onChanged?: () => void
}

/** Loads one conversation and drives streaming replies for it. `conversationId === null` is a new, unsaved chat. */
export function useChat(conversationId: number | null, { onTitle, onChanged }: Options = {}) {
  const [conversation, setConversation] = useState<ConversationDetail | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  // Set when we create a conversation ourselves, so the route change doesn't reload over the live stream.
  const createdHereRef = useRef<number | null>(null)

  const load = useCallback(async (id: number) => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await conversations.get(id)
      setConversation(data)
      setMessages(data.messages)
    } catch (e) {
      setLoadError(e instanceof ApiError && e.status === 404 ? 'This conversation does not exist or was deleted.' : String((e as Error).message))
    } finally {
      setLoading(false)
    }
  }, [])

  // Reset during render when switching to a new chat (React's recommended alternative to setState in an effect).
  const [prevId, setPrevId] = useState(conversationId)
  if (prevId !== conversationId) {
    setPrevId(conversationId)
    if (conversationId === null) {
      setConversation(null)
      setMessages([])
      setLoadError(null)
    }
  }

  useEffect(() => {
    if (conversationId === null) return
    if (createdHereRef.current === conversationId) {
      createdHereRef.current = null
      return
    }
    void load(conversationId)
  }, [conversationId, load])

  useEffect(() => () => abortRef.current?.abort(), [])

  const patch = (id: number, update: Partial<Message> | ((m: Message) => Partial<Message>)) =>
    setMessages((list) => list.map((m) => (m.id === id ? { ...m, ...(typeof update === 'function' ? update(m) : update) } : m)))

  /** Streams one reply. Returns an error message if the request was rejected before streaming began. */
  const run = useCallback(
    async (convId: number, path: string, body: object, userDraftId: number | null): Promise<string | null> => {
      const assistant = draft('assistant', '', 'streaming')
      let assistantId = assistant.id
      setMessages((list) => [...list, assistant])
      setStreaming(true)
      const controller = new AbortController()
      abortRef.current = controller

      const onEvent = ({ event, data }: SSEEvent) => {
        if (event === 'user_message' && userDraftId !== null) {
          patch(userDraftId, { id: data.id as number })
          if (typeof data.title === 'string') onTitle?.(convId, data.title)
        } else if (event === 'start') {
          const realId = data.assistant_message_id as number
          patch(assistantId, { id: realId, model_id: data.model_id as string })
          assistantId = realId
        } else if (event === 'tool') {
          const call = { id: data.call_id as string, name: data.name as string, args: data.args as Record<string, unknown>,
            status: data.status as ToolCall['status'], summary: data.summary as string }
          patch(assistantId, (m) => {
            const calls = [...(m.tool_calls ?? [])]
            const i = calls.findIndex((c) => c.id === call.id)
            if (i === -1) calls.push(call)
            else calls[i] = call
            const artifact = data.artifact as Artifact | null
            return { tool_calls: calls, artifacts: artifact ? [...(m.artifacts ?? []), artifact] : m.artifacts }
          })
        } else if (event === 'status') {
          patch(assistantId, { stage: { ...(data as { stage: 'generating' }), since: Date.now() } })
        } else if (event === 'sources') {
          patch(assistantId, { grounding: data as unknown as GroundingInfo })
        } else if (event === 'delta') {
          patch(assistantId, (m) => ({ content: m.content + (data.text as string) }))
        } else if (event === 'done') {
          patch(assistantId, {
            status: data.status as Message['status'],
            model_id: data.model_id as string,
            input_tokens: data.input_tokens as number,
            output_tokens: data.output_tokens as number,
            cost_usd: data.cost_usd as string | null,
            stop_reason: data.stop_reason as string,
            error_kind: (data.error_kind as string) ?? '',
            error_message: (data.error_message as string) ?? '',
            citations: (data.citations as SourceRef[]) ?? [],
            invalid_citations: (data.invalid_citations as string[]) ?? [],
            first_token_ms: data.first_token_ms as number | null,
            duration_ms: data.duration_ms as number | null,
          })
        } else if (event === 'error') {
          patch(assistantId, {
            status: 'error',
            error_kind: data.kind as string,
            error_message: data.message as string,
          })
        }
      }

      try {
        await postStream(path, body, onEvent, controller.signal)
        return null
      } catch (e) {
        if (controller.signal.aborted) {
          patch(assistantId, { status: 'stopped', stop_reason: 'stopped' })
          return null
        }
        if (e instanceof ApiError) {
          // Rejected before streaming (validation, rate limit, ...): undo the optimistic messages.
          setMessages((list) => list.filter((m) => m.id !== assistantId && m.id !== userDraftId))
          return e.message
        }
        patch(assistantId, {
          status: 'error',
          error_kind: 'network',
          error_message: 'The connection was interrupted. Retry to generate the reply again.',
        })
        return null
      } finally {
        abortRef.current = null
        setStreaming(false)
        onChanged?.()
      }
    },
    [onTitle, onChanged],
  )

  const send = useCallback(
    async (content: string, modelId: string, ensureConversation: () => Promise<number>, webSearch = false) => {
      const userDraft = draft('user', content)
      setMessages((list) => [...list, userDraft])
      let convId: number
      try {
        convId = conversationId ?? (await ensureConversation())
      } catch (e) {
        setMessages((list) => list.filter((m) => m.id !== userDraft.id))
        return (e as Error).message
      }
      if (conversationId === null) createdHereRef.current = convId
      return run(convId, `/api/conversations/${convId}/messages/`, { content, model_id: modelId, web_search: webSearch }, userDraft.id)
    },
    [conversationId, run],
  )

  const regenerate = useCallback(
    async (modelId: string, webSearch = false) => {
      if (conversationId === null) return null
      setMessages((list) => {
        const lastUser = list.map((m) => m.role).lastIndexOf('user')
        return lastUser === -1 ? list : list.slice(0, lastUser + 1)
      })
      return run(conversationId, `/api/conversations/${conversationId}/regenerate/`, { model_id: modelId, web_search: webSearch }, null)
    },
    [conversationId, run],
  )

  const edit = useCallback(
    async (messageId: number, content: string, modelId: string, webSearch = false) => {
      if (conversationId === null) return null
      setMessages((list) => {
        const i = list.findIndex((m) => m.id === messageId)
        return i === -1 ? list : [...list.slice(0, i), { ...list[i], content }]
      })
      return run(
        conversationId,
        `/api/conversations/${conversationId}/messages/${messageId}/edit/`,
        { content, model_id: modelId, web_search: webSearch },
        null,
      )
    },
    [conversationId, run],
  )

  const stop = useCallback(() => abortRef.current?.abort(), [])

  return { conversation, messages, loading, loadError, streaming, send, regenerate, edit, stop, reload: load }
}
