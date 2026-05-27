import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { checkAppPassword, clearAppPassword, getAppPassword, setAppPassword } from '../lib/auth'

export default function LoginGate({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(() => getAppPassword() !== null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  // Validate a password persisted from a previous session; if the backend
  // password changed, re-lock so the user is prompted again.
  useEffect(() => {
    const stored = getAppPassword()
    if (!stored) return
    let active = true
    void checkAppPassword(stored).then((ok) => {
      if (active && !ok) {
        clearAppPassword()
        setUnlocked(false)
      }
    })
    return () => {
      active = false
    }
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!password || submitting) return
    setSubmitting(true)
    setError(false)
    const ok = await checkAppPassword(password)
    setSubmitting(false)
    if (ok) {
      setAppPassword(password)
      setUnlocked(true)
    } else {
      setError(true)
      setPassword('')
    }
  }

  if (unlocked) return <>{children}</>

  return (
    <div className="flex h-dvh items-center justify-center bg-background p-4">
      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="w-full max-w-sm space-y-4 rounded-xl border bg-card p-6 shadow-sm"
      >
        <div className="space-y-1">
          <h1 className="text-lg font-semibold">Job Hunt</h1>
          <p className="text-sm text-muted-foreground">Enter the password to continue.</p>
        </div>
        <Input
          type="password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          aria-invalid={error}
        />
        {error && <p className="text-sm text-destructive">Incorrect password.</p>}
        <Button type="submit" className="w-full" disabled={submitting || !password}>
          {submitting ? 'Checking…' : 'Unlock'}
        </Button>
      </form>
    </div>
  )
}
