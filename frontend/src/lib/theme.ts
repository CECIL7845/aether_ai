import { useCallback, useEffect, useState } from 'react'

export type ThemeChoice = 'system' | 'light' | 'dark'

function read(): ThemeChoice {
  try {
    const t = localStorage.getItem('theme')
    return t === 'light' || t === 'dark' ? t : 'system'
  } catch {
    return 'system'
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeChoice>(read)
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') delete root.dataset.theme
    else root.dataset.theme = theme
    try {
      if (theme === 'system') localStorage.removeItem('theme')
      else localStorage.setItem('theme', theme)
    } catch {
      // storage unavailable (private mode): theme still applies for this session
    }
  }, [theme])
  const setTheme = useCallback((t: ThemeChoice) => setThemeState(t), [])
  return { theme, setTheme }
}
