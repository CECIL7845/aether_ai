import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { CircleAlert, CircleCheck, X } from 'lucide-react'
import clsx from 'clsx'

type Toast = { id: number; kind: 'error' | 'success'; text: string }
const ToastContext = createContext<(kind: Toast['kind'], text: string) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), [])
  const push = useCallback(
    (kind: Toast['kind'], text: string) => {
      const id = Date.now() + Math.random()
      setToasts((t) => [...t.slice(-2), { id, kind, text }])
      setTimeout(() => dismiss(id), kind === 'error' ? 7000 : 3500)
    },
    [dismiss],
  )
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className={clsx(
              'pointer-events-auto flex max-w-md items-start gap-2 rounded-xl border px-4 py-3 text-sm shadow-card',
              t.kind === 'error' ? 'border-danger/30 bg-danger-soft text-danger' : 'border-border bg-surface text-text',
            )}
          >
            {t.kind === 'error' ? <CircleAlert className="mt-0.5 size-4 shrink-0" /> : <CircleCheck className="mt-0.5 size-4 shrink-0 text-success" />}
            <span className="flex-1">{t.text}</span>
            <button onClick={() => dismiss(t.id)} aria-label="Dismiss notification" className="opacity-70 hover:opacity-100">
              <X className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const useToast = () => useContext(ToastContext)
