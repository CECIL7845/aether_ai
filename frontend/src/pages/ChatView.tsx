import { Download, MessageSquareText } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { conversations } from '../api/endpoints'
import type { ModelsResponse } from '../api/types'
import { Composer } from '../components/Composer'
import { MessageItem } from '../components/MessageItem'
import { ModelPicker } from '../components/ModelPicker'
import { Spinner } from '../components/ui'
import { useChat } from '../hooks/useChat'
import { useToast } from '../lib/toast'

const STARTERS = [
  'Explain retrieval-augmented generation with a simple example',
  'Review this function for bugs and edge cases',
  'Draft a polite follow-up email to a client about an unpaid invoice',
  'Compare PostgreSQL and MongoDB for an analytics workload',
]

export function ChatView({
  conversationId,
  models,
  onTitle,
  onChanged,
}: {
  conversationId: number | null
  models: ModelsResponse | null
  onTitle: (id: number, title: string) => void
  onChanged: () => void
}) {
  const navigate = useNavigate()
  const toast = useToast()
  const chat = useChat(conversationId, { onTitle, onChanged })
  // The user's explicit model choice, remembered per conversation (null = new, unsaved chat).
  const [picked, setPicked] = useState<{ forId: number | null; id: string } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  // Model: explicit choice, else the conversation's last model if still available, else the deployment default.
  const available = models?.models.filter((m) => m.available).map((m) => m.id) ?? []
  const preferred = chat.conversation?.model_id
  const fallback = preferred && available.includes(preferred) ? preferred : (models?.default ?? available[0] ?? '')
  const modelId = picked && picked.forId === conversationId && available.includes(picked.id) ? picked.id : fallback
  const setModelId = (id: string) => setPicked({ forId: conversationId, id })

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [chat.messages])

  useEffect(() => {
    stickToBottom.current = true
  }, [conversationId])

  const ensureConversation = useCallback(async () => {
    const created = await conversations.create(modelId)
    setPicked({ forId: created.id, id: modelId })
    navigate(`/c/${created.id}`, { replace: false })
    onChanged()
    return created.id
  }, [modelId, navigate, onChanged])

  const report = (error: string | null | undefined) => {
    if (error) toast('error', error)
    return error
  }

  const send = async (text: string) => {
    stickToBottom.current = true
    return report(await chat.send(text, modelId, ensureConversation))
  }

  const lastAssistantId = [...chat.messages].reverse().find((m) => m.role === 'assistant')?.id
  const empty = chat.messages.length === 0

  if (chat.loadError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <MessageSquareText className="size-10 text-faint" />
        <p className="text-muted">{chat.loadError}</p>
        <button className="text-sm font-medium text-accent hover:underline" onClick={() => navigate('/')}>
          Start a new chat
        </button>
      </div>
    )
  }

  const composer = (
    <Composer
      onSend={send}
      onStop={chat.stop}
      streaming={chat.streaming}
      autoFocus
      toolbar={
        models && <ModelPicker models={models.models} value={modelId} onChange={setModelId} disabled={chat.streaming} />
      }
    />
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {conversationId !== null && chat.conversation && (
        <div className="flex items-center justify-end gap-1 px-4 pt-2 max-md:hidden">
          <a
            href={conversations.exportUrl(conversationId, 'md')}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-muted hover:bg-surface-2 hover:text-text"
          >
            <Download className="size-3.5" /> Export
          </a>
        </div>
      )}
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
        }}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        {chat.loading ? (
          <div className="flex justify-center py-16 text-muted">
            <Spinner className="size-6" />
          </div>
        ) : empty ? (
          <div className="mx-auto flex h-full max-w-2xl flex-col justify-center px-4 py-10">
            <h1 className="text-center text-2xl font-semibold tracking-tight sm:text-3xl">What are you working on?</h1>
            <p className="mt-2 text-center text-sm text-muted">
              Answers come from the selected AI model and can be wrong. Check important facts.
            </p>
            <div className="mt-8">{composer}</div>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {STARTERS.map((s) => (
                <button
                  key={s}
                  onClick={() => void send(s)}
                  disabled={chat.streaming || !modelId}
                  className="rounded-xl border border-border bg-surface px-3.5 py-3 text-left text-sm text-muted transition-colors hover:border-accent/40 hover:text-text"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <section aria-label="Messages" className="mx-auto max-w-3xl space-y-7 px-4 py-6">
            {chat.messages.map((m) => (
              <MessageItem
                key={m.id}
                message={m}
                models={models?.models ?? []}
                isLastAssistant={m.id === lastAssistantId}
                busy={chat.streaming}
                onEdit={async (id, content) => {
                  stickToBottom.current = true
                  report(await chat.edit(id, content, modelId))
                }}
                onRegenerate={async () => {
                  stickToBottom.current = true
                  report(await chat.regenerate(modelId))
                }}
              />
            ))}
          </section>
        )}
      </div>
      {!empty && !chat.loading && (
        <div className="mx-auto w-full max-w-3xl px-4 pt-2 pb-4">
          {composer}
          <p className="mt-2 text-center text-xs text-faint">AI can make mistakes. Verify important information.</p>
        </div>
      )}
    </div>
  )
}
