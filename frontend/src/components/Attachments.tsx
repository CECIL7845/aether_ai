import clsx from 'clsx'
import { FileSpreadsheet, FileText, FileCode, Library, Paperclip, Upload, X, CircleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { ACCEPTED_FILES, documents as documentsApi } from '../api/endpoints'
import type { AttachedDocument, DocumentInfo } from '../api/types'
import { STATUS_LABEL } from '../lib/files'
import { IconButton, Spinner } from './ui'

export function KindIcon({ kind, className }: { kind: string; className?: string }) {
  const Icon = kind === 'xlsx' || kind === 'csv' ? FileSpreadsheet : kind === 'text' ? FileCode : FileText
  return <Icon className={clsx('size-4 shrink-0', className)} aria-hidden="true" />
}

export function AttachmentChips({
  items,
  onRemove,
  disabled,
}: {
  items: AttachedDocument[]
  onRemove: (id: number) => void
  disabled?: boolean
}) {
  if (!items.length) return null
  return (
    <ul className="flex flex-wrap gap-1.5 px-3 pt-3" aria-label="Attached documents">
      {items.map((d) => (
        <li
          key={d.id}
          title={d.status === 'failed' ? d.error : `${d.title} — ${STATUS_LABEL[d.status]}`}
          className={clsx(
            'flex max-w-60 items-center gap-1.5 rounded-lg border py-1 pr-1 pl-2 text-xs',
            d.status === 'failed' ? 'border-danger/40 bg-danger-soft text-danger' : 'border-border bg-surface-2 text-text',
          )}
        >
          {d.status === 'queued' || d.status === 'processing' ? (
            <Spinner className="size-3" />
          ) : d.status === 'failed' ? (
            <CircleAlert className="size-3.5 shrink-0" />
          ) : (
            <KindIcon kind={d.kind} className="text-muted" />
          )}
          <span className="truncate">{d.title}</span>
          <span className="sr-only">({STATUS_LABEL[d.status]})</span>
          <button
            type="button"
            onClick={() => onRemove(d.id)}
            disabled={disabled}
            aria-label={`Remove ${d.title} from this chat`}
            className="rounded p-0.5 text-faint hover:bg-surface-3 hover:text-text disabled:opacity-40"
          >
            <X className="size-3.5" />
          </button>
        </li>
      ))}
    </ul>
  )
}

export function AttachMenu({
  attachedIds,
  onUpload,
  onPick,
  disabled,
}: {
  attachedIds: number[]
  onUpload: (files: File[]) => void
  onPick: (doc: DocumentInfo) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [library, setLibrary] = useState<DocumentInfo[] | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    documentsApi
      .list()
      .then((p) => setLibrary(p.results))
      .catch(() => setLibrary([]))
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !root.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])

  const available = (library ?? []).filter((d) => d.status === 'ready' && !attachedIds.includes(d.id)).slice(0, 8)
  const item = 'flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-surface-2'

  return (
    <div ref={root} className="relative">
      <IconButton label="Attach documents" aria-haspopup="menu" aria-expanded={open} disabled={disabled} onClick={() => setOpen((o) => !o)}>
        <Paperclip className="size-4.5" />
      </IconButton>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPTED_FILES}
        className="hidden"
        data-testid="file-input"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          e.target.value = ''
          if (files.length) onUpload(files)
        }}
      />
      {open && (
        <div role="menu" className="absolute bottom-full left-0 z-20 mb-2 w-72 rounded-xl border border-border bg-surface p-1 shadow-card">
          <button role="menuitem" className={item} onClick={() => { setOpen(false); input.current?.click() }}>
            <Upload className="size-4" /> Upload files…
          </button>
          <div className="my-1 border-t border-border" />
          <p className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-faint">
            <Library className="size-3.5" /> From your documents
          </p>
          {library === null ? (
            <div className="px-2.5 py-2 text-muted">
              <Spinner />
            </div>
          ) : available.length === 0 ? (
            <p className="px-2.5 py-2 text-xs text-faint">No other ready documents.</p>
          ) : (
            available.map((d) => (
              <button key={d.id} role="menuitem" className={item} onClick={() => { setOpen(false); onPick(d) }}>
                <KindIcon kind={d.kind} className="text-muted" />
                <span className="truncate">{d.title}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
