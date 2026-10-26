import { ArrowUp, Square } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import clsx from 'clsx'

export const MAX_CHARS = 32_000

export function Composer({
  onSend,
  onStop,
  streaming,
  disabled,
  toolbar,
  autoFocus,
}: {
  onSend: (text: string) => Promise<string | null | undefined> | void
  onStop: () => void
  streaming: boolean
  disabled?: boolean
  toolbar?: ReactNode
  autoFocus?: boolean
}) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  }, [text])

  const tooLong = text.length > MAX_CHARS
  const canSend = !!text.trim() && !tooLong && !streaming && !disabled

  const submit = async () => {
    if (!canSend) return
    const value = text
    setText('')
    const error = await onSend(value)
    if (error) setText(value) // request was rejected: give the text back
    ref.current?.focus()
  }

  return (
    <div className="rounded-2xl border border-border bg-surface shadow-card focus-within:border-accent/70 focus-within:ring-3 focus-within:ring-accent/15">
      <label htmlFor="composer" className="sr-only">
        Message
      </label>
      <textarea
        id="composer"
        ref={ref}
        rows={1}
        value={text}
        autoFocus={autoFocus}
        placeholder="Ask anything…"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            void submit()
          }
        }}
        className="block max-h-60 w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-[15px] leading-relaxed outline-none placeholder:text-faint focus-visible:outline-none"
      />
      <div className="flex items-center justify-between gap-2 px-2 pb-2">
        <div className="flex min-w-0 items-center gap-1">{toolbar}</div>
        <div className="flex items-center gap-2">
          {text.length > MAX_CHARS * 0.8 && (
            <span className={clsx('text-xs', tooLong ? 'text-danger' : 'text-faint')} aria-live="polite">
              {text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}
            </span>
          )}
          {streaming ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generating"
              title="Stop generating"
              className="inline-flex size-9 items-center justify-center rounded-xl bg-text text-bg hover:opacity-85"
            >
              <Square className="size-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!canSend}
              aria-label="Send message"
              title="Send (Enter) · New line (Shift+Enter)"
              className="inline-flex size-9 items-center justify-center rounded-xl bg-accent text-accent-contrast transition-opacity hover:bg-accent-strong disabled:opacity-35"
            >
              <ArrowUp className="size-4.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
