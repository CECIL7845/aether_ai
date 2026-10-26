import clsx from 'clsx'
import { Download, FileUp, RotateCcw, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ACCEPTED_FILES, documents as documentsApi } from '../api/endpoints'
import type { DocumentInfo } from '../api/types'
import { KindIcon } from '../components/Attachments'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { Button, IconButton, Spinner } from '../components/ui'
import { formatBytes, STATUS_LABEL } from '../lib/files'
import { useToast } from '../lib/toast'

const statusStyle: Record<string, string> = {
  ready: 'bg-success/10 text-success',
  failed: 'bg-danger-soft text-danger',
  queued: 'bg-surface-3 text-muted',
  processing: 'bg-accent-soft text-accent',
}

export function DocumentsView() {
  const toast = useToast()
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null)
  const [busy, setBusy] = useState(0)
  const [toDelete, setToDelete] = useState<DocumentInfo | null>(null)
  const input = useRef<HTMLInputElement>(null)

  const load = useCallback(
    () =>
      documentsApi
        .list()
        .then((page) => setDocs(page.results))
        .catch((e: Error) => toast('error', e.message)),
    [toast],
  )

  useEffect(() => {
    documentsApi
      .list()
      .then((page) => setDocs(page.results))
      .catch((e: Error) => toast('error', e.message))
  }, [toast])

  const pending = docs?.some((d) => d.status === 'queued' || d.status === 'processing')
  useEffect(() => {
    if (!pending) return
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [pending, load])

  const upload = async (files: File[]) => {
    setBusy((n) => n + files.length)
    for (const f of files) {
      try {
        await documentsApi.upload(f)
      } catch (e) {
        toast('error', `${f.name}: ${(e as Error).message}`)
      } finally {
        setBusy((n) => n - 1)
      }
    }
    await load()
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">Documents</h1>
            <p className="mt-1 text-sm text-muted">Files you upload are private to your account. Attach them to a chat to ask questions about them.</p>
          </div>
          <Button onClick={() => input.current?.click()} disabled={busy > 0}>
            {busy > 0 ? <Spinner /> : <FileUp className="size-4" />} Upload
          </Button>
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPTED_FILES}
            className="hidden"
            aria-label="Upload documents"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? [])
              e.target.value = ''
              if (files.length) void upload(files)
            }}
          />
        </div>

        {docs === null ? (
          <div className="flex justify-center py-16 text-muted">
            <Spinner className="size-6" />
          </div>
        ) : docs.length === 0 ? (
          <div className="mt-8 rounded-2xl border border-dashed border-border p-10 text-center">
            <FileUp className="mx-auto size-8 text-faint" />
            <p className="mt-3 font-medium">No documents yet</p>
            <p className="mt-1 text-sm text-muted">Upload PDF, Word, Excel, CSV, text or code files (up to 20 MB each).</p>
          </div>
        ) : (
          <ul className="mt-6 divide-y divide-border rounded-2xl border border-border bg-surface" aria-label="Your documents">
            {docs.map((d) => (
              <li key={d.id} className="flex items-center gap-3 px-4 py-3">
                <KindIcon kind={d.kind} className="size-5 text-muted" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{d.title}</p>
                  <p className="text-xs text-faint">
                    {formatBytes(d.size)}
                    {d.page_count ? ` · ${d.page_count} page${d.page_count === 1 ? '' : 's'}` : ''}
                    {d.status === 'ready' && !d.embedding_model ? ' · keyword search only' : ''}
                  </p>
                  {d.status === 'failed' && <p className="mt-0.5 text-xs text-danger">{d.error}</p>}
                </div>
                <span className={clsx('rounded-full px-2 py-0.5 text-xs font-medium', statusStyle[d.status])}>
                  {STATUS_LABEL[d.status]}
                </span>
                {d.status === 'failed' && (
                  <IconButton
                    label={`Retry processing ${d.title}`}
                    onClick={async () => {
                      try {
                        await documentsApi.reprocess(d.id)
                        await load()
                      } catch (e) {
                        toast('error', (e as Error).message)
                      }
                    }}
                  >
                    <RotateCcw className="size-4" />
                  </IconButton>
                )}
                <a
                  href={documentsApi.downloadUrl(d.id)}
                  aria-label={`Download ${d.title}`}
                  title="Download"
                  className="inline-flex size-8 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-text"
                >
                  <Download className="size-4" />
                </a>
                <IconButton label={`Delete ${d.title}`} onClick={() => setToDelete(d)}>
                  <Trash2 className="size-4" />
                </IconButton>
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmDialog
        open={toDelete !== null}
        title="Delete document?"
        body={`“${toDelete?.title ?? ''}” and its search index will be permanently deleted and removed from any chats.`}
        confirmLabel="Delete"
        onCancel={() => setToDelete(null)}
        onConfirm={async () => {
          const d = toDelete
          setToDelete(null)
          if (!d) return
          try {
            await documentsApi.remove(d.id)
            setDocs((list) => list?.filter((x) => x.id !== d.id) ?? null)
            toast('success', 'Document deleted.')
          } catch (e) {
            toast('error', (e as Error).message)
          }
        }}
      />
    </div>
  )
}
