import { BookOpen, ChevronDown, ExternalLink, Globe, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import type { Message, SourceRef } from '../api/types'

function SourceItem({ c }: { c: SourceRef }) {
  return (
    <li className="text-xs">
      <p className="flex flex-wrap items-center gap-x-1.5">
        <span className="rounded bg-accent-soft px-1.5 py-0.5 font-mono font-medium text-accent">{c.ref}</span>
        {c.url ? (
          <a href={c.url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 font-medium hover:underline">
            {c.title} <ExternalLink className="size-3" />
          </a>
        ) : (
          <span className="font-medium">{c.title}</span>
        )}
        {c.location && <span className="text-faint">· {c.location}</span>}
        {!c.retrieved && <span className="rounded bg-warning-soft px-1.5 text-warning">snippet only</span>}
      </p>
      <blockquote className="mt-1 border-l-2 border-border pl-2 text-muted">{c.snippet}</blockquote>
    </li>
  )
}

export function Sources({ message }: { message: Message }) {
  const [open, setOpen] = useState(false)
  const g = message.grounding
  const cited = message.citations ?? []
  const invalid = message.invalid_citations ?? []
  const web = g?.web
  const pagesRead = web?.pages.filter((p) => p.status === 'read').length ?? 0
  if (!cited.length && !invalid.length && !g) return null

  return (
    <div className="mt-3 space-y-2 text-sm">
      {web && (
        <p className="flex items-center gap-1.5 text-xs text-faint">
          <Globe className="size-3.5" />
          {web.error ? (
            <span className="text-warning">Web search failed: {web.error}</span>
          ) : (
            <span>
              Searched the web for “{web.query}” · read {pagesRead} of {web.pages.length} page{web.pages.length === 1 ? '' : 's'}
            </span>
          )}
        </p>
      )}
      {g?.skipped?.map((s) => (
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
              · {[...new Set(cited.map((c) => (c.url ? new URL(c.url).hostname : c.title)))].join(', ')}
            </span>
            <ChevronDown className={`ml-auto size-3.5 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
          </button>
          {open && (
            <ol className="space-y-2.5 border-t border-border px-3 py-2.5">
              {cited.map((c) => (
                <SourceItem key={c.ref} c={c} />
              ))}
            </ol>
          )}
        </div>
      ) : (
        g &&
        message.status === 'complete' &&
        (g.mode === 'full' || g.mode === 'search' || (web && !web.error)) && (
          <p className="text-xs text-faint">No sources were cited in this answer.</p>
        )
      )}
    </div>
  )
}
