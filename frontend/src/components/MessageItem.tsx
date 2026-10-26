import { CircleAlert, Pencil, RefreshCw, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import clsx from 'clsx'
import type { Message, ModelInfo } from '../api/types'
import { formatCost, formatTokens } from '../lib/format'
import { CopyButton, Markdown } from './Markdown'
import { Sources } from './Sources'
import { Button, IconButton } from './ui'

const ERROR_HINTS: Record<string, string> = {
  quota: 'Usage limit reached',
  rate_limit: 'Provider rate limit',
  unavailable: 'Provider unavailable',
  auth: 'Provider configuration problem',
  busy: 'Another reply is in progress',
  refusal: 'Model declined',
  network: 'Connection lost',
}

export function MessageItem({
  message,
  models,
  isLastAssistant,
  busy,
  onEdit,
  onRegenerate,
}: {
  message: Message
  models: ModelInfo[]
  isLastAssistant: boolean
  busy: boolean
  onEdit: (id: number, content: string) => void
  onRegenerate: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(message.content)

  if (message.role === 'user') {
    if (editing) {
      return (
        <div className="ml-auto w-full max-w-[85%]">
          <label htmlFor={`edit-${message.id}`} className="sr-only">
            Edit message
          </label>
          <textarea
            id={`edit-${message.id}`}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
            rows={Math.min(10, value.split('\n').length + 1)}
            className="w-full resize-y rounded-2xl border border-accent/60 bg-surface px-4 py-3 text-[15px] outline-none"
          />
          <p className="mt-1 text-xs text-faint">Saving replaces this message and discards the replies after it.</p>
          <div className="mt-2 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => { setEditing(false); setValue(message.content) }}>
              Cancel
            </Button>
            <Button
              disabled={!value.trim() || busy}
              onClick={() => {
                setEditing(false)
                onEdit(message.id, value)
              }}
            >
              Save & regenerate
            </Button>
          </div>
        </div>
      )
    }
    return (
      <div className="group flex flex-col items-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent-soft px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-text">
          {message.content}
        </div>
        <div className="mt-1 flex gap-0.5 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 max-md:opacity-100">
          <CopyButton text={message.content} />
          {message.id > 0 && (
            <IconButton label="Edit message" disabled={busy} onClick={() => { setValue(message.content); setEditing(true) }}>
              <Pencil className="size-3.5" />
            </IconButton>
          )}
        </div>
      </div>
    )
  }

  const model = models.find((m) => m.id === message.model_id)
  const cost = formatCost(message.cost_usd)
  return (
    <div className="group">
      {message.content ? (
        <Markdown content={message.content} />
      ) : message.status === 'streaming' ? (
        <div className="flex h-7 items-center gap-1" aria-label="Generating reply">
          {[0, 150, 300].map((d) => (
            <span key={d} className="size-1.5 animate-bounce rounded-full bg-faint" style={{ animationDelay: `${d}ms` }} />
          ))}
        </div>
      ) : null}

      {message.status === 'streaming' && message.content && (
        <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-accent align-middle" aria-hidden="true" />
      )}

      {message.status === 'error' && (
        <div role="alert" className="mt-2 flex items-start gap-2 rounded-xl border border-danger/30 bg-danger-soft px-3.5 py-2.5 text-sm text-danger">
          <CircleAlert className="mt-0.5 size-4 shrink-0" />
          <div className="flex-1">
            <p className="font-medium">{ERROR_HINTS[message.error_kind] ?? 'The reply failed'}</p>
            <p className="opacity-90">{message.error_message}</p>
          </div>
          {isLastAssistant && message.error_kind !== 'quota' && (
            <Button variant="secondary" className="shrink-0 !py-1" onClick={onRegenerate} disabled={busy}>
              <RotateCcw className="size-3.5" /> Retry
            </Button>
          )}
        </div>
      )}

      {message.status !== 'streaming' && <Sources message={message} />}

      {message.status === 'stopped' && (
        <p className="mt-2 text-xs text-faint">
          {message.content ? 'Stopped — the reply above is incomplete.' : 'Stopped before any reply was generated.'}
        </p>
      )}

      {message.status !== 'streaming' && message.status !== 'error' && (
        <div
          className={clsx(
            'mt-1.5 flex flex-wrap items-center gap-x-1 gap-y-1 text-xs text-faint transition-opacity',
            !isLastAssistant && 'opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 max-md:opacity-100',
          )}
        >
          {message.content && <CopyButton text={message.content} />}
          {isLastAssistant && (
            <IconButton label="Regenerate reply" onClick={onRegenerate} disabled={busy}>
              <RefreshCw className="size-3.5" />
            </IconButton>
          )}
          <span className="ml-1">{model?.label ?? message.model_id}</span>
          {message.input_tokens != null && (
            <span title="Input / output tokens reported by the provider">
              · {formatTokens(message.input_tokens)} in / {formatTokens(message.output_tokens)} out
            </span>
          )}
          {cost && <span title="Estimated from list prices">· {cost}</span>}
        </div>
      )}
    </div>
  )
}
