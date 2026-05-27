import { useEffect, useState } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { AuthContext, type AuthRole } from '@/contexts/auth-context'
import { supabase } from '@/lib/supabase'

interface AuthProviderProps {
  children: React.ReactNode
}

async function fetchRole(accessToken: string): Promise<AuthRole | null> {
  const response = await fetch('/api/auth/me', {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!response.ok) return null
  const data = (await response.json()) as { role: string }
  return data.role === 'admin' ? 'admin' : 'regular'
}

const PREVIEW_STORAGE_KEY = 'fulcrum-preview-as-regular'

function readPreviewFromStorage(): boolean {
  try {
    return localStorage.getItem(PREVIEW_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

function writePreviewToStorage(value: boolean): void {
  try {
    if (value) {
      localStorage.setItem(PREVIEW_STORAGE_KEY, 'true')
    } else {
      localStorage.removeItem(PREVIEW_STORAGE_KEY)
    }
  } catch {
    // localStorage unavailable
  }
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [session, setSession] = useState<Session | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [role, setRole] = useState<AuthRole | null>(null)
  const [previewAsRegular, setPreviewAsRegularState] = useState<boolean>(readPreviewFromStorage)
  const [loading, setLoading] = useState(true)

  const setPreviewAsRegular = (value: boolean): void => {
    writePreviewToStorage(value)
    setPreviewAsRegularState(value)
  }

  useEffect(() => {
    let cancelled = false

    void supabase.auth.getSession().then(async ({ data }) => {
      if (cancelled) return
      setSession(data.session)
      setUser(data.session?.user ?? null)
      if (data.session) {
        setRole(await fetchRole(data.session.access_token))
      }
      setLoading(false)
    })

    const { data: subscription } = supabase.auth.onAuthStateChange(async (_event, newSession) => {
      if (cancelled) return
      setSession(newSession)
      setUser(newSession?.user ?? null)
      setRole(newSession ? await fetchRole(newSession.access_token) : null)
    })

    return () => {
      cancelled = true
      subscription.subscription.unsubscribe()
    }
  }, [])

  const login = async (email: string, password: string): Promise<void> => {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
  }

  const logout = async (): Promise<void> => {
    setPreviewAsRegular(false)
    await supabase.auth.signOut()
  }

  const effectiveRole: AuthRole | null = role === 'admin' && previewAsRegular ? 'regular' : role

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        role,
        effectiveRole,
        previewAsRegular,
        setPreviewAsRegular,
        isAuthenticated: session !== null,
        loading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
