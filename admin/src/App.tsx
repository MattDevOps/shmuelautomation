import { useEffect, useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type HealthStatus = 'unknown' | 'ok' | 'unreachable'

function App() {
  const [status, setStatus] = useState<HealthStatus>('unknown')

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((data: { status: string }) => setStatus(data.status === 'ok' ? 'ok' : 'unreachable'))
      .catch(() => setStatus('unreachable'))
  }, [])

  return (
    <main>
      <h1>Classic Jerusalem Realty — Admin</h1>
      <p>
        Backend status: <strong data-testid="health-status">{status}</strong>
      </p>
    </main>
  )
}

export default App
