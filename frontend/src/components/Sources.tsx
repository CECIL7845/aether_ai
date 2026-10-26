import { BookOpen, ChevronDown, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import type { Message } from '../api/types'

export function Sources({ message }: { message: Message }) {
  const [open, setOpen] = useState(false)
  const g = message.grounding
  const cited = message.citations ?? []
  const invalid = message.invalid_citations ?? []
  if (!cited.length && !invalid.length && !g?.skipped.length && !(g && message.status === 'complete')) return null

  return (
    <div className="mt-3 space-y-2 text-sm">
      {g?.skipped.map((s) => (
        <p key={s.title} className="flex items-center gap-1.5 text-xs text-warning">
          <TriangleAlert className="size-3.5" /> “{s.title}” was {s.status === 'failed' ? 'unreadable' : 'still processing'} and
          was not used.
        </p>
      ))}
      {invalid.length > 0 && (
        <p role="note" className="flex items-start gap-1.5 rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          This answer cites {invalid.join(', ')}, which {invalid.length === 1 ? 'does' : 'do'} not match any provided
          source. Treat those claims with caution.
        </p>
      )}
      {cited.length > 0 ? (
        <div className="rounded-xl border border-border">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-muted hover:text-text"
          >
            <BookOpen className="size-3.5" />
            {cited.length} source{cited.length === 1 ? '' : 's'} cited
            <span className="truncate font-normal text-faint">
              · {[...new Set(cited.map((c) => c.title))].join(', ')}
            </span>
            <ChevronDown className={`ml-auto size-3.5 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
          </button>
          {open && (
            <ol className="space-y-2 border-t border-border px-3 py-2.5">
              {cited.map((c) => (
                <li key={c.ref} className="text-xs">
                  <p>
                    <span className="mr-1.5 rounded bg-accent-soft px-1.5 py-0.5 font-mono font-medium text-accent">{c.ref}</span>
                    <span className="font-medium">{c.title}</span>
                    {c.location && <span className="text-faint"> · {c.location}</span>}
                  </p>
                  <blockquote className="mt-1 border-l-2 border-border pl-2 text-muted">{c.snippet}</blockquote>
                </li>
              ))}
            </ol>
          )}
        </div>
      ) : (
        g &&
        message.status === 'complete' &&
        g.mode !== 'none' && (
          <p className="text-xs text-faint">No document sources were cited in this answer.</p>
        )
      )}
    </div>
  )
}
