import { Download, FileUp, Globe, MessageSquareText } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { conversations, documents as documentsApi } from '../api/endpoints'
import type { AttachedDocument, DocumentInfo, ModelsResponse } from '../api/types'
import { AttachMenu, AttachmentChips } from '../components/Attachments'
import { Composer } from '../components/Composer'
import { MessageItem } from '../components/MessageItem'
import { ModelPicker } from '../components/ModelPicker'
import { IconButton, Spinner } from '../components/ui'
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

  // Documents attached to this chat. For a new chat they are kept locally and sent when it is created.
  const [attached, setAttached] = useState<AttachedDocument[]>([])
  const [attachedFor, setAttachedFor] = useState<number | null>(null)
  const [uploading, setUploading] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [webSearch, setWebSearch] = useState(false)
  const webAvailable = models?.features.web_search ?? false
  const useWeb = webSearch && webAvailable
  const [prevConversationId, setPrevConversationId] = useState(conversationId)
  if (prevConversationId !== conversationId) {
    // Switching chats: clear, unless this is the chat we just created from a new one (attachments carry over).
    setPrevConversationId(conversationId)
    if (conversationId === null || attachedFor !== conversationId) {
      setAttachedFor(null)
      setAttached([])
    }
  } else if (chat.conversation && chat.conversation.id === conversationId && attachedFor !== conversationId) {
    setAttachedFor(conversationId)
    setAttached(chat.conversation.documents)
  }

  const attachedRef = useRef<AttachedDocument[]>([])
  useLayoutEffect(() => {
    attachedRef.current = attached
  }, [attached])
  const persistAttachments = async (change: (list: AttachedDocument[]) => AttachedDocument[]) => {
    const next = change(attachedRef.current)
    attachedRef.current = next
    setAttached(next)
    if (conversationId !== null) {
      try {
        await conversations.update(conversationId, { document_ids: next.map((d) => d.id) })
      } catch (e) {
        toast('error', (e as Error).message)
      }
    }
  }

  const uploadFiles = async (files: File[]) => {
    setUploading((n) => n + files.length)
    const added: AttachedDocument[] = []
    for (const file of files) {
      try {
        added.push(await documentsApi.upload(file))
      } catch (e) {
        toast('error', `${file.name}: ${(e as Error).message}`)
      } finally {
        setUploading((n) => n - 1)
      }
    }
    if (added.length) await persistAttachments((list) => [...list, ...added])
  }

  const pick = (doc: DocumentInfo) => void persistAttachments((list) => [...list, doc])
  const detach = (id: number) => void persistAttachments((list) => list.filter((d) => d.id !== id))

  // Poll documents that are still being processed.
  const pending = attached.filter((d) => d.status === 'queued' || d.status === 'processing').map((d) => d.id)
  const pendingKey = pending.join(',')
  useEffect(() => {
    if (!pendingKey) return
    const ids = pendingKey.split(',').map(Number)
    const timer = setInterval(async () => {
      const updates = await Promise.allSettled(ids.map((id) => documentsApi.get(id)))
      setAttached((list) =>
        list.map((d) => {
          const u = updates.find((r) => r.status === 'fulfilled' && r.value.id === d.id)
          return u && u.status === 'fulfilled' ? { ...d, status: u.value.status, error: u.value.error } : d
        }),
      )
    }, 2000)
    return () => clearInterval(timer)
  }, [pendingKey])

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
    const created = await conversations.create({ model_id: modelId, document_ids: attachedRef.current.map((d) => d.id) })
    setPicked({ forId: created.id, id: modelId })
    setAttachedFor(created.id)
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
    return report(await chat.send(text, modelId, ensureConversation, useWeb))
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
      attachments={
        <>
          <AttachmentChips items={attached} onRemove={detach} disabled={chat.streaming} />
          {uploading > 0 && (
            <p className="flex items-center gap-1.5 px-4 pt-2 text-xs text-muted" role="status">
              <Spinner className="size-3" /> Uploading {uploading} file{uploading === 1 ? '' : 's'}…
            </p>
          )}
        </>
      }
      toolbar={
        <>
          <AttachMenu attachedIds={attached.map((d) => d.id)} onUpload={uploadFiles} onPick={pick} disabled={chat.streaming} />
          <IconButton
            label={webAvailable ? (useWeb ? 'Web search on' : 'Web search off') : 'Web search is not configured on this workspace'}
            aria-pressed={useWeb}
            disabled={!webAvailable || chat.streaming}
            onClick={() => setWebSearch((v) => !v)}
            className={useWeb ? '!bg-accent-soft !text-accent' : ''}
          >
            <Globe className="size-4.5" />
          </IconButton>
          {models && <ModelPicker models={models.models} value={modelId} onChange={setModelId} disabled={chat.streaming} />}
        </>
      }
    />
  )

  return (
    <div
      className="relative flex min-h-0 flex-1 flex-col"
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes('Files')) {
          e.preventDefault()
          setDragging(true)
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        const files = Array.from(e.dataTransfer.files)
        if (files.length) void uploadFiles(files)
      }}
    >
      {dragging && (
        <div className="pointer-events-none absolute inset-3 z-30 flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-accent bg-accent-soft/90 text-accent">
          <FileUp className="size-8" />
          <p className="font-medium">Drop files to attach them to this chat</p>
          <p className="text-xs">PDF, Word, Excel, CSV, text and code files</p>
        </div>
      )}
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
                  report(await chat.edit(id, content, modelId, useWeb))
                }}
                onRegenerate={async () => {
                  stickToBottom.current = true
                  report(await chat.regenerate(modelId, useWeb))
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
