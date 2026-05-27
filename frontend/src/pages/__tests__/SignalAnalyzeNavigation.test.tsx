import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/helpers'
import type { TaskOutput, SignalPayload } from '@/lib/queries'

// Mock AppSidebar
vi.mock('@/components/AppSidebar', () => ({
  default: () => <div data-testid="sidebar" />,
}))

// Mock queries
const mockFetchTaskOutputs = vi.fn<() => Promise<TaskOutput[]>>()
const mockCreateConversation = vi.fn<() => Promise<{ conversation_id: string }>>()

vi.mock('@/lib/queries', async (importOriginal) => {
  return {
    ...(await importOriginal()),
    fetchTaskOutputs: (...args: unknown[]) => mockFetchTaskOutputs(...(args as [])),
    updateTaskOutputState: vi.fn().mockResolvedValue(undefined),
    createConversation: (...args: unknown[]) => mockCreateConversation(...(args as [])),
  }
})

// Mock navigate
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  return { ...(await importOriginal()), useNavigate: () => mockNavigate }
})

import SignalsDashboard from '../SignalsDashboard'

function makeSignal(overrides: Partial<SignalPayload> = {}): TaskOutput {
  const payload: SignalPayload = {
    title: 'Test Signal',
    prompt: 'Analyze this metric',
    severity: 'medium',
    category: 'test',
    state: 'active',
    ...overrides,
  }
  return {
    id: crypto.randomUUID(),
    task_name: 'generate-signals',
    toolbox: 'sales',
    payload: payload as unknown as Record<string, unknown>,
    created_at: new Date().toISOString(),
  }
}

describe('Signal → Chat Navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('creates a conversation and navigates to /chat with correct state on Analyze', async () => {
    const user = userEvent.setup()
    const signal = makeSignal({
      title: 'Revenue anomaly',
      prompt: 'Why did revenue drop 15% in Q3?',
    })
    mockFetchTaskOutputs.mockResolvedValue([signal])
    mockCreateConversation.mockResolvedValue({ conversation_id: 'new-conv-456' })

    renderWithProviders(<SignalsDashboard toolbox="sales" />)

    await waitFor(() => {
      expect(screen.getByText('Revenue anomaly')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /analyze/i }))

    await waitFor(() => {
      expect(mockCreateConversation).toHaveBeenCalledTimes(1)
    })

    expect(mockNavigate).toHaveBeenCalledWith('/sales/chat', {
      state: {
        conversationId: 'new-conv-456',
        initialPrompt: 'Why did revenue drop 15% in Q3?',
      },
    })
  })

  it('passes the correct signal prompt, not the title', async () => {
    const user = userEvent.setup()
    const signal = makeSignal({
      title: 'Metric spike',
      prompt: 'Investigate the 3x spike in error rate since Tuesday',
    })
    mockFetchTaskOutputs.mockResolvedValue([signal])
    mockCreateConversation.mockResolvedValue({ conversation_id: 'conv-789' })

    renderWithProviders(<SignalsDashboard toolbox="sales" />)

    await waitFor(() => {
      expect(screen.getByText('Metric spike')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /analyze/i }))

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/sales/chat', {
        state: {
          conversationId: 'conv-789',
          initialPrompt: 'Investigate the 3x spike in error rate since Tuesday',
        },
      })
    })
  })

  it('waits for createConversation before navigating', async () => {
    const user = userEvent.setup()
    const signal = makeSignal({ title: 'Slow create' })
    mockFetchTaskOutputs.mockResolvedValue([signal])

    // Delay the conversation creation
    let resolveCreate!: (value: { conversation_id: string }) => void
    mockCreateConversation.mockReturnValue(
      new Promise((resolve) => {
        resolveCreate = resolve
      })
    )

    renderWithProviders(<SignalsDashboard toolbox="sales" />)

    await waitFor(() => {
      expect(screen.getByText('Slow create')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /analyze/i }))

    // createConversation called but navigate not yet
    expect(mockCreateConversation).toHaveBeenCalled()
    expect(mockNavigate).not.toHaveBeenCalled()

    // Now resolve the creation
    resolveCreate({ conversation_id: 'delayed-conv' })

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/sales/chat', {
        state: {
          conversationId: 'delayed-conv',
          initialPrompt: (signal.payload as unknown as SignalPayload).prompt,
        },
      })
    })
  })

  it('handles multiple signals — Analyze targets the correct signal prompt', async () => {
    const user = userEvent.setup()
    const signal1 = makeSignal({ title: 'Signal A', prompt: 'Prompt A' })
    const signal2 = makeSignal({ title: 'Signal B', prompt: 'Prompt B' })
    mockFetchTaskOutputs.mockResolvedValue([signal1, signal2])
    mockCreateConversation.mockResolvedValue({ conversation_id: 'conv-multi' })

    renderWithProviders(<SignalsDashboard toolbox="sales" />)

    await waitFor(() => {
      expect(screen.getByText('Signal A')).toBeInTheDocument()
      expect(screen.getByText('Signal B')).toBeInTheDocument()
    })

    // Click Analyze on the second signal
    const analyzeButtons = screen.getAllByRole('button', { name: /analyze/i })
    await user.click(analyzeButtons[1])

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/sales/chat', {
        state: {
          conversationId: 'conv-multi',
          initialPrompt: 'Prompt B',
        },
      })
    })
  })
})
