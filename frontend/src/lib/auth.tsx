import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, ensureCsrf } from '../api/client'
import { auth } from '../api/endpoints'
import type { User } from '../api/types'

type AuthState = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, displayName: string) => Promise<void>
  logout: () => Promise<void>
  setUser: (u: User) => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ensureCsrf()
      .then(() => auth.me())
      .then(setUser)
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 403)) console.error(e)
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setUser(await auth.login(email, password))
  }, [])
  const register = useCallback(async (email: string, password: string, displayName: string) => {
    setUser(await auth.register(email, password, displayName))
  }, [])
  const logout = useCallback(async () => {
    await auth.logout()
    setUser(null)
    await ensureCsrf(true)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout, setUser }),
    [user, loading, login, register, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
