import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router'
import { useAuth } from '../lib/auth'
import { Button, Logo, Spinner } from '../components/ui'

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { user, login, register } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={(location.state as { from?: string } | null)?.from ?? '/'} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'login') await login(email, password)
      else await register(email, password, name)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const field = 'mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm outline-none focus:border-accent'
  return (
    <main className="flex min-h-full items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Logo className="text-xl" />
        </div>
        <div className="rounded-2xl border border-border bg-surface p-6 shadow-card">
          <h1 className="text-lg font-semibold">{mode === 'login' ? 'Sign in' : 'Create your account'}</h1>
          <p className="mt-1 text-sm text-muted">
            {mode === 'login' ? 'Welcome back.' : 'Start a private AI workspace in seconds.'}
          </p>
          <form onSubmit={submit} className="mt-5 space-y-4" noValidate>
            {mode === 'register' && (
              <div>
                <label htmlFor="name" className="text-sm font-medium">
                  Name <span className="font-normal text-faint">(optional)</span>
                </label>
                <input id="name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" className={field} />
              </div>
            )}
            <div>
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                className={field}
              />
            </div>
            <div>
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                aria-describedby={mode === 'register' ? 'pw-hint' : undefined}
                className={field}
              />
              {mode === 'register' && (
                <p id="pw-hint" className="mt-1 text-xs text-faint">
                  At least 10 characters. Avoid common passwords.
                </p>
              )}
            </div>
            {error && (
              <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
                {error}
              </p>
            )}
            <Button type="submit" className="w-full !py-2.5" disabled={busy || !email || !password}>
              {busy && <Spinner />}
              {mode === 'login' ? 'Sign in' : 'Create account'}
            </Button>
          </form>
        </div>
        <p className="mt-5 text-center text-sm text-muted">
          {mode === 'login' ? (
            <>
              New here?{' '}
              <Link to="/register" className="font-medium text-accent hover:underline">
                Create an account
              </Link>
            </>
          ) : (
            <>
              Already have an account?{' '}
              <Link to="/login" className="font-medium text-accent hover:underline">
                Sign in
              </Link>
            </>
          )}
        </p>
      </div>
    </main>
  )
}
