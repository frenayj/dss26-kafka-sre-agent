import { Suspense, lazy, useEffect, useState } from 'react'
import App from './App.tsx'

// Lazy so the dashboard bundle doesn't carry React Flow.
const ArchitecturePage = lazy(() => import('./pages/ArchitecturePage.tsx'))
const PagerDutyPage = lazy(() => import('./pages/PagerDutyPage.tsx'))
const OpsPage = lazy(() => import('./pages/OpsPage.tsx'))

// Minimal hash router: the app is a single view, plus hidden presenter pages
// at #/architecture, #/pagerduty and #/ops (not linked from the UI - navigate
// by URL).
export default function Root() {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])
  if (hash.startsWith('#/architecture')) {
    return (
      <Suspense fallback={null}>
        <ArchitecturePage />
      </Suspense>
    )
  }
  if (hash.startsWith('#/pagerduty')) {
    return (
      <Suspense fallback={null}>
        <PagerDutyPage />
      </Suspense>
    )
  }
  if (hash.startsWith('#/ops')) {
    return (
      <Suspense fallback={null}>
        <OpsPage />
      </Suspense>
    )
  }
  return <App />
}
