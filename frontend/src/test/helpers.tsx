import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderOptions } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { AuthContext, type AuthContextType, type AuthRole } from '@/contexts/auth-context'

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
}

function buildAuthValue(role: AuthRole): AuthContextType {
  return {
    user: { id: 'test-user', email: `${role}@example.com` } as AuthContextType['user'],
    session: null,
    role,
    effectiveRole: role,
    previewAsRegular: false,
    setPreviewAsRegular: vi.fn(),
    isAuthenticated: true,
    loading: false,
    login: vi.fn(() => Promise.resolve()),
    logout: vi.fn(() => Promise.resolve()),
  }
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'> & { route?: string; authRole?: AuthRole }
) {
  const queryClient = createTestQueryClient()
  const { route = '/', authRole = 'admin', ...renderOptions } = options ?? {}
  const authValue = buildAuthValue(authRole)

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthContext.Provider value={authValue}>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>
    )
  }

  return { ...render(ui, { wrapper: Wrapper, ...renderOptions }), queryClient }
}
