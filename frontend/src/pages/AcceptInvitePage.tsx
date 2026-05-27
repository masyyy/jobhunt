import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '@/lib/supabase'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

export default function AcceptInvitePage() {
  const navigate = useNavigate()
  const [hasSession, setHasSession] = useState(false)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Supabase invite links arrive as either:
  //   /accept-invite?code=...           (PKCE flow — must exchange for a session)
  //   /accept-invite#access_token=...   (implicit flow — SDK auto-processes)
  // Handle both, then watch the session state.
  useEffect(() => {
    let cancelled = false

    const init = async () => {
      const url = new URL(window.location.href)
      const code = url.searchParams.get('code')
      if (code) {
        const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)
        if (cancelled) return
        if (exchangeError) {
          setError(exchangeError.message)
        } else {
          // Strip the code from the URL so a refresh doesn't re-attempt the exchange.
          window.history.replaceState({}, '', url.pathname)
        }
      }
      const { data } = await supabase.auth.getSession()
      if (!cancelled) setHasSession(data.session !== null)
    }
    void init()

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!cancelled) setHasSession(session !== null)
    })
    return () => {
      cancelled = true
      subscription.subscription.unsubscribe()
    }
  }, [])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    // Client-side floor only — Supabase project policy (HIBP, complexity)
    // is the real gate. Keep both in sync; see CLAUDE.md > Authentication.
    if (password.length < 12) {
      setError('Password must be at least 12 characters')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      const { error: updateError } = await supabase.auth.updateUser({ password })
      if (updateError) throw updateError
      void navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm border border-border shadow-lg">
        <CardHeader className="text-center">
          <CardTitle className="text-xl">Set your password</CardTitle>
          <CardDescription>
            Choose a password to finish creating your account. Use at least 12 characters.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!hasSession ? (
            <p className="text-sm text-muted-foreground text-center">
              This invite link is invalid or has expired. Ask an admin for a new one.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="New password"
                autoComplete="new-password"
                autoFocus
                required
              />
              <Input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Confirm password"
                autoComplete="new-password"
                required
              />
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button
                type="submit"
                disabled={loading || !password || !confirm}
                size="lg"
                className="w-full"
              >
                {loading ? 'Setting password...' : 'Continue'}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
