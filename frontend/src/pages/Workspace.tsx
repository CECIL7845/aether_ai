import { Menu, PanelLeftOpen, Plus } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useMatch, useNavigate } from 'react-router'
import clsx from 'clsx'
import { conversations as conversationsApi, models as modelsApi } from '../api/endpoints'
import type { Conversation, ModelsResponse } from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { Sidebar } from '../components/Sidebar'
import { IconButton, Logo } from '../components/ui'
import { useAuth } from '../lib/auth'
import type { ThemeChoice } from '../lib/theme'
import { useToast } from '../lib/toast'
import { ChatView } from './ChatView'
import { SettingsView } from './SettingsView'

export function Workspace({ theme, setTheme }: { theme: ThemeChoice; setTheme: (t: ThemeChoice) => void }) {
  const { user, logout } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const chatMatch = useMatch('/c/:id')
  const settingsMatch = useMatch('/settings')
  const activeId = chatMatch ? Number(chatMatch.params.id) : null

  const [items, setItems] = useState<Conversation[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [models, setModels] = useState<ModelsResponse | null>(null)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [desktopOpen, setDesktopOpen] = useState(true)
  const [toDelete, setToDelete] = useState<Conversation | null>(null)

  const refresh = useCallback(async () => {
    try {
      const page = await conversationsApi.list({ q: query.trim() || undefined, archived: showArchived })
      setItems(page.results)
    } catch (e) {
      toast('error', (e as Error).message)
    } finally {
      setListLoading(false)
    }
  }, [query, showArchived, toast])

  useEffect(() => {
    const t = setTimeout(refresh, query ? 250 : 0)
    return () => clearTimeout(t)
  }, [refresh, query])

  useEffect(() => {
    modelsApi.list().then(setModels).catch((e) => toast('error', e.message))
  }, [toast])

  const onTitle = useCallback((id: number, title: string) => {
    setItems((list) => list.map((c) => (c.id === id ? { ...c, title } : c)))
  }, [])

  const rename = async (id: number, title: string) => {
    try {
      const updated = await conversationsApi.update(id, { title })
      setItems((list) => list.map((c) => (c.id === id ? updated : c)))
    } catch (e) {
      toast('error', (e as Error).message)
    }
  }

  const archive = async (id: number, archived: boolean) => {
    try {
      await conversationsApi.update(id, { archived })
      setItems((list) => list.filter((c) => c.id !== id))
      toast('success', archived ? 'Conversation archived.' : 'Conversation restored.')
      if (archived && id === activeId) navigate('/')
    } catch (e) {
      toast('error', (e as Error).message)
    }
  }

  const confirmDelete = async () => {
    const target = toDelete
    setToDelete(null)
    if (!target) return
    try {
      await conversationsApi.remove(target.id)
      setItems((list) => list.filter((c) => c.id !== target.id))
      toast('success', 'Conversation deleted.')
      if (target.id === activeId) navigate('/')
    } catch (e) {
      toast('error', (e as Error).message)
    }
  }

  const sidebar = (
    <Sidebar
      items={items}
      loading={listLoading}
      activeId={activeId}
      query={query}
      onQuery={setQuery}
      showArchived={showArchived}
      onShowArchived={setShowArchived}
      onRename={rename}
      onArchive={archive}
      onDelete={setToDelete}
      onNavigate={() => setMobileOpen(false)}
      onClose={() => (window.matchMedia('(min-width: 768px)').matches ? setDesktopOpen(false) : setMobileOpen(false))}
      userLabel={user?.display_name || user?.email || ''}
      onLogout={async () => {
        await logout()
        navigate('/login')
      }}
    />
  )

  return (
    <div className="flex h-full">
      {/* Desktop sidebar */}
      <aside className={clsx('hidden w-72 shrink-0 border-r border-border md:block', !desktopOpen && 'md:hidden')}>{sidebar}</aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} aria-hidden="true" />
          <aside className="absolute inset-y-0 left-0 w-[min(20rem,85vw)] border-r border-border shadow-card">{sidebar}</aside>
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-1 border-b border-border px-2 md:border-0">
          <IconButton label="Open sidebar" onClick={() => setMobileOpen(true)} className="md:hidden">
            <Menu className="size-5" />
          </IconButton>
          {!desktopOpen && (
            <IconButton label="Open sidebar" onClick={() => setDesktopOpen(true)} className="max-md:hidden">
              <PanelLeftOpen className="size-4.5" />
            </IconButton>
          )}
          <Link to="/" className="md:hidden" aria-label="Home">
            <Logo className="text-sm" />
          </Link>
          <span className="ml-1 min-w-0 truncate text-sm font-medium text-muted max-md:hidden">
            {activeId ? items.find((c) => c.id === activeId)?.title : ''}
          </span>
          <div className="flex-1" />
          <Link to="/" aria-label="New chat" title="New chat" className="inline-flex size-8 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-text md:hidden">
            <Plus className="size-5" />
          </Link>
        </header>

        {settingsMatch ? (
          <SettingsView theme={theme} setTheme={setTheme} models={models} />
        ) : (
          <ChatView conversationId={activeId} models={models} onTitle={onTitle} onChanged={refresh} />
        )}
      </main>

      <ConfirmDialog
        open={toDelete !== null}
        title="Delete conversation?"
        body={`“${toDelete?.title ?? ''}” and all its messages will be permanently deleted. This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setToDelete(null)}
      />
    </div>
  )
}
