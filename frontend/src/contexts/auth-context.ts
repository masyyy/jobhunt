import { createContext } from 'react'
import type { Session, User } from '@supabase/supabase-js'

export type AuthRole = 'admin' | 'regular'

export interface AuthContextType {
  user: User | null
  session: Session | null
  role: AuthRole | null
  effectiveRole: AuthRole | null
  previewAsRegular: boolean
  setPreviewAsRegular: (value: boolean) => void
  isAuthenticated: boolean
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextType | null>(null)
