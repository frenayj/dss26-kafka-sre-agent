import { useCallback, useState } from "react"

function readStored(storageKey: string, fallback: boolean): boolean {
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (raw === "true") return true
    if (raw === "false") return false
  } catch {
    // localStorage disabled - fall back to default.
  }
  return fallback
}

/**
 * Boolean panel open/close state persisted to localStorage under a stable key.
 * Mirrors the shadcn `useSidebar()` `open`/`setOpen`/`toggle` ergonomics, but
 * keyed so we can run multiple independent sidebars side-by-side. The stored
 * value is read once, as the initial state, so the first render is already
 * correct (no open-then-collapse flash).
 */
export function usePanelOpen(
  key: string,
  defaultOpen = true,
): { open: boolean; setOpen: (next: boolean) => void; toggle: () => void } {
  const storageKey = `ui.panel.${key}.open`
  const [open, setOpenState] = useState(() => readStored(storageKey, defaultOpen))

  const setOpen = useCallback(
    (next: boolean) => {
      setOpenState(next)
      try {
        window.localStorage.setItem(storageKey, String(next))
      } catch {
        // ignore
      }
    },
    [storageKey],
  )

  const toggle = useCallback(() => setOpen(!open), [open, setOpen])

  return { open, setOpen, toggle }
}
