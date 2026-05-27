import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// Stub Supabase env so `src/lib/supabase.ts` doesn't throw on import.
// Tests never make real network calls — anything that touches Supabase is
// either mocked or wrapped via the AuthProvider.
vi.stubEnv('VITE_SUPABASE_URL', 'http://localhost:54321')
vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'test-anon-key')

// Mock URL.createObjectURL / revokeObjectURL (used by prompt-input attachments)
URL.createObjectURL = vi.fn(() => 'blob:mock-url')
URL.revokeObjectURL = vi.fn()

// Mock use-stick-to-bottom (needs real scroll measurement, unavailable in jsdom)
vi.mock('use-stick-to-bottom', () => ({
  StickToBottom: Object.assign(
    ({ children, ...props }: Record<string, unknown>) => {
      const { className, role } = props as { className?: string; role?: string }
      return (
        <div className={className} role={role} data-testid="stick-to-bottom">
          {children as React.ReactNode}
        </div>
      )
    },
    {
      Content: ({ children, ...props }: Record<string, unknown>) => {
        const { className } = props as { className?: string }
        return (
          <div className={className} data-testid="stick-to-bottom-content">
            {children as React.ReactNode}
          </div>
        )
      },
    }
  ),
  useStickToBottomContext: () => ({
    isAtBottom: true,
    scrollToBottom: vi.fn(),
  }),
}))

// Mock streamdown and plugins (Shiki loads WASM, not available in jsdom)
vi.mock('streamdown', () => ({
  Streamdown: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="streamdown">{children}</div>
  ),
}))

vi.mock('@streamdown/code', () => ({ code: () => ({}) }))
vi.mock('@streamdown/math', () => ({ math: () => ({}) }))
vi.mock('@streamdown/mermaid', () => ({ mermaid: () => ({}) }))
vi.mock('@streamdown/cjk', () => ({ cjk: () => ({}) }))
