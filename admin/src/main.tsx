import * as Sentry from '@sentry/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN
if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.MODE,
    // Errors-only to start. Performance traces add data-volume and the free
    // tier is generous on errors but tighter on traces — flip on if needed.
    tracesSampleRate: 0,
    sendDefaultPii: false,
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Sentry.ErrorBoundary
      fallback={({ error, resetError }) => (
        <main style={{ padding: '2rem', maxWidth: '40rem', margin: '0 auto' }}>
          <h1>Something went wrong.</h1>
          <p style={{ color: 'var(--ink-soft)' }}>
            The error has been reported. You can try again, or refresh the
            page if the problem persists.
          </p>
          <pre
            style={{
              background: 'var(--paper-deep)',
              padding: '1rem',
              borderRadius: 6,
              overflow: 'auto',
              fontSize: '0.85rem',
            }}
          >
            {error instanceof Error ? error.message : String(error)}
          </pre>
          <button
            type="button"
            onClick={resetError}
            style={{
              marginTop: '1rem',
              padding: '0.5rem 1rem',
              background: 'var(--clay)',
              color: 'white',
              border: 0,
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Try again
          </button>
        </main>
      )}
    >
      <App />
    </Sentry.ErrorBoundary>
  </StrictMode>,
)
