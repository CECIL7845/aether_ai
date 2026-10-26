import clsx from 'clsx'
import {
  Archive,
  ArchiveRestore,
  Check,
  Download,
  LogOut,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  Plus,
  Search,
  Settings,
  Trash2,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { conversations as conversationsApi } from '../api/endpoints'
import type { Conversation } from '../api/types'
import { dateGroup } from '../lib/format'
import { IconButton, Logo, Spinner } from './ui'

type Props = {
  items: Conversation[]
  loading: boolean
  activeId: number | null
  query: string
  onQuery: (q: string) => void
  showArchived: boolean
  onShowArchived: (v: boolean) => void
  onRename: (id: number, title: string) => void
  onArchive: (id: number, archived: boolean) => void
  onDelete: (c: Conversation) => void
  onNavigate: () => void
  onClose: () => void
  userLabel: string
  onLogout: () => void
}

export function Sidebar(props: Props) {
  const { items, loading, activeId, query, onQuery, showArchived, onShowArchived } = props
  const groups: [string, Conversation[]][] = []
  for (const c of items) {
    const g = dateGroup(c.updated_at)
    const last = groups[groups.length - 1]
    if (last && last[0] === g) last[1].push(c)
    else groups.push([g, [c]])
  }

  return (
    <nav aria-label="Conversations" className="flex h-full flex-col bg-surface">
      <div className="flex items-center justify-between px-3 pt-3 pb-2">
        <Link to="/" onClick={props.onNavigate} aria-label="Home">
          <Logo />
        </Link>
        <IconButton label="Close sidebar" onClick={props.onClose}>
          <PanelLeftClose className="size-4.5" />
        </IconButton>
      </div>

      <div className="px-3">
        <Link
          to="/"
          onClick={props.onNavigate}
          className="flex w-full items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-surface-2"
        >
          <Plus className="size-4" /> New chat
        </Link>
        <div className="relative mt-2">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-faint" />
          <label htmlFor="conv-search" className="sr-only">
            Search conversations
          </label>
          <input
            id="conv-search"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder="Search"
            className="w-full rounded-lg bg-surface-2 py-2 pr-8 pl-8 text-sm outline-none placeholder:text-faint focus:ring-1 focus:ring-accent/50"
          />
          {query && (
            <button
              onClick={() => onQuery('')}
              aria-label="Clear search"
              className="absolute top-1/2 right-2 -translate-y-1/2 text-faint hover:text-text"
            >
              <X className="size-4" />
            </button>
          )}
        </div>
        <div className="mt-2 flex gap-1 text-xs" role="tablist" aria-label="Conversation filter">
          {[false, true].map((archived) => (
            <button
              key={String(archived)}
              role="tab"
              aria-selected={showArchived === archived}
              onClick={() => onShowArchived(archived)}
              className={clsx(
                'rounded-md px-2 py-1',
                showArchived === archived ? 'bg-surface-3 font-medium text-text' : 'text-muted hover:text-text',
              )}
            >
              {archived ? 'Archived' : 'Recent'}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2 flex-1 overflow-y-auto px-2 pb-2">
        {loading && items.length === 0 ? (
          <div className="flex justify-center py-6 text-muted">
            <Spinner />
          </div>
        ) : items.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-faint">
            {query ? 'No conversations match your search.' : showArchived ? 'No archived conversations.' : 'No conversations yet.'}
          </p>
        ) : (
          groups.map(([label, list]) => (
            <section key={label} className="mt-2">
              <h3 className="px-2 pb-1 text-xs font-medium text-faint">{label}</h3>
              <ul>
                {list.map((c) => (
                  <ConversationRow key={c.id} c={c} active={c.id === activeId} {...props} />
                ))}
              </ul>
            </section>
          ))
        )}
      </div>

      <div className="border-t border-border p-2">
        <Link
          to="/settings"
          onClick={props.onNavigate}
          className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-text"
        >
          <Settings className="size-4" />
          <span className="flex-1 truncate">{props.userLabel}</span>
        </Link>
        <button
          onClick={props.onLogout}
          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-text"
        >
          <LogOut className="size-4" /> Sign out
        </button>
      </div>
    </nav>
  )
}

function ConversationRow({ c, active, onRename, onArchive, onDelete, onNavigate }: Props & { c: Conversation; active: boolean }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [title, setTitle] = useState(c.title)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !menuRef.current?.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [menuOpen])

  if (renaming) {
    const save = () => {
      setRenaming(false)
      if (title.trim() && title.trim() !== c.title) onRename(c.id, title.trim())
      else setTitle(c.title)
    }
    return (
      <li className="flex items-center gap-1 px-1 py-0.5">
        <label htmlFor={`rename-${c.id}`} className="sr-only">
          Conversation title
        </label>
        <input
          id={`rename-${c.id}`}
          autoFocus
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') save()
            if (e.key === 'Escape') {
              setTitle(c.title)
              setRenaming(false)
            }
          }}
          onBlur={save}
          className="min-w-0 flex-1 rounded-md border border-accent/60 bg-surface px-2 py-1.5 text-sm outline-none"
        />
        <IconButton label="Save title" onMouseDown={(e) => e.preventDefault()} onClick={save}>
          <Check className="size-4" />
        </IconButton>
      </li>
    )
  }

  const item = 'flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-surface-2'
  return (
    <li className="group relative">
      <Link
        to={`/c/${c.id}`}
        onClick={onNavigate}
        aria-current={active ? 'page' : undefined}
        className={clsx(
          'block truncate rounded-lg py-2 pr-9 pl-2.5 text-sm',
          active ? 'bg-surface-3 font-medium text-text' : 'text-muted hover:bg-surface-2 hover:text-text',
        )}
      >
        {c.title}
      </Link>
      <div ref={menuRef} className="absolute top-1/2 right-1 -translate-y-1/2">
        <IconButton
          label={`Options for ${c.title}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((o) => !o)}
          className={clsx('size-7', !menuOpen && !active && 'opacity-0 group-hover:opacity-100 focus:opacity-100 max-md:opacity-100')}
        >
          <MoreHorizontal className="size-4" />
        </IconButton>
        {menuOpen && (
          <div role="menu" className="absolute right-0 z-20 mt-1 w-48 rounded-xl border border-border bg-surface p-1 shadow-card">
            <button role="menuitem" className={item} onClick={() => { setMenuOpen(false); setRenaming(true) }}>
              <Pencil className="size-4" /> Rename
            </button>
            <button role="menuitem" className={item} onClick={() => { setMenuOpen(false); onArchive(c.id, !c.archived) }}>
              {c.archived ? <ArchiveRestore className="size-4" /> : <Archive className="size-4" />}
              {c.archived ? 'Unarchive' : 'Archive'}
            </button>
            <a role="menuitem" className={item} href={conversationsApi.exportUrl(c.id, 'md')} onClick={() => setMenuOpen(false)}>
              <Download className="size-4" /> Export Markdown
            </a>
            <a role="menuitem" className={item} href={conversationsApi.exportUrl(c.id, 'txt')} onClick={() => setMenuOpen(false)}>
              <Download className="size-4" /> Export text
            </a>
            <button role="menuitem" className={clsx(item, 'text-danger')} onClick={() => { setMenuOpen(false); onDelete(c) }}>
              <Trash2 className="size-4" /> Delete
            </button>
          </div>
        )}
      </div>
    </li>
  )
}
