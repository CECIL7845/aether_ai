import { Navigate, Route, Routes, useLocation } from 'react-router'
import { Spinner } from './components/ui'
import { useAuth } from './lib/auth'
import { useTheme } from './lib/theme'
import { AuthPage } from './pages/AuthPage'
import { Workspace } from './pages/Workspace'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-muted">
        <Spinner className="size-6" />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

export default function App() {
  const { theme, setTheme } = useTheme()
  const workspace = (
    <RequireAuth>
      <Workspace theme={theme} setTheme={setTheme} />
    </RequireAuth>
  )
  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      {/* One Workspace element for all app routes so chat state survives navigation from "/" to "/c/:id". */}
      <Route path="/*" element={workspace} />
    </Routes>
  )
}
