import { createContext, useContext, useEffect, useState } from "react"

type Theme = "dark" | "light" | "system"

interface ThemeProviderProps {
  children: React.ReactNode
  defaultTheme?: Theme
  storageKey?: string
}

interface ThemeProviderState {
  theme: Theme
  /** Theme with "system" resolved to the actual mode - what's on <html>. */
  resolvedTheme: "dark" | "light"
  setTheme: (theme: Theme) => void
}

const initialState: ThemeProviderState = {
  theme: "light",
  resolvedTheme: "light",
  setTheme: () => null,
}

const ThemeProviderContext = createContext<ThemeProviderState>(initialState)

function systemTheme(): "dark" | "light" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light"
}

export function ThemeProvider({
  children,
  defaultTheme = "light",
  storageKey = "ui.theme",
  ...props
}: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => {
    try {
      return (window.localStorage.getItem(storageKey) as Theme) || defaultTheme
    } catch {
      return defaultTheme
    }
  })

  const resolvedTheme = theme === "system" ? systemTheme() : theme

  useEffect(() => {
    const root = window.document.documentElement
    const apply = () => {
      root.classList.remove("light", "dark")
      root.classList.add(theme === "system" ? systemTheme() : theme)
    }
    apply()
    if (theme !== "system") return
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    mq.addEventListener("change", apply)
    return () => mq.removeEventListener("change", apply)
  }, [theme])

  const setTheme = (next: Theme) => {
    try {
      window.localStorage.setItem(storageKey, next)
    } catch {
      // localStorage disabled - theme just won't persist.
    }
    setThemeState(next)
  }

  return (
    <ThemeProviderContext.Provider
      {...props}
      value={{ theme, resolvedTheme, setTheme }}
    >
      {children}
    </ThemeProviderContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeProviderContext)
  if (context === undefined)
    throw new Error("useTheme must be used within a ThemeProvider")
  return context
}
