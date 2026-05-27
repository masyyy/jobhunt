import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/helpers'
import type { TaskOutput, SignalPayload } from '@/lib/queries'

// Mock AppSidebar — has complex dependencies irrelevant to these tests
vi.mock('@/components/AppSidebar', () => ({
  default: () => <div data-testid="sidebar" />,
}))

// Mock queries module so we control data
const mockFetchTaskOutputs = vi.fn<() => Promise<TaskOutput[]>>()
const mockUpdateTaskOutputState = vi.fn<() => Promise<void>>()
const mockCreateConversation = vi.fn<() => Promise<{ conversation_id: string }>>()

vi.mock('@/lib/queries', async (importOriginal) => {
  return {
    ...(await importOriginal()),
    fetchTaskOutputs: (...args: unknown[]) => mockFetchTaskOutputs(...(args as [])),
    updateTaskOutputState: (...args: unknown[]) => mockUpdateTaskOutputState(...(args as [])),
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

describe('SignalsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUpdateTaskOutputState.mockResolvedValue(undefined)
  })

  it('shows skeletons while loading, then renders signals', async () => {
    const signals = [
      makeSignal({ severity: 'high', title: 'Critical issue' }),
      makeSignal({ severity: 'medium', title: 'Warning issue' }),
      makeSignal({ severity: 'low', title: 'Optimization tip' }),
    ]
    mockFetchTaskOutputs.mockResolvedValue(signals)

    renderWithProviders(<SignalsDashboard toolbox="sales" />)

    // Stats and signals should appear
    await waitFor(() => {
      expect(screen.getByText('Critical issue')).toBeInTheDocument()
    })

    expect(screen.getByText('Warning issue')).toBeInTheDocument()
    expect(screen.getByText('Optimization tip')).toBeInTheDocument()
  })

  it('computes stats cards correctly from signal data', async () => {
    const signals = [
      makeSignal({ severity: 'high', state: 'active' }),
      makeSignal({ severity: 'high', state: 'active' }),
      makeSignal({ severity: 'medium', state: 'active' }),
      makeSignal({ severity: 'low', state: 'dismissed' }),
    ]
    mockFetchTaskOutputs.mockResolvedValue(signals)

    renderWithProviders(<SignalsDashboard toolbox="sales" />)

    await waitFor(() => {
      // Active Signals count = 3 (only active ones)
      expect(screen.getByText('3')).toBeInTheDocument()
    })
    // Critical Faults = 2 (high + active)
    expect(screen.getByText('02')).toBeInTheDocument()
    // Anomalies = 1 (medium + active)
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('toggles between active and archive views', async () => {
    const signals = [
      makeSignal({ state: 'active', title: 'Active one' }),
      makeSignal({ state: 'dismissed', title: 'Dismissed one' }),
    ]
    mockFetchTaskOutputs.mockResolvedValue(signals)

    renderWithProviders(<SignalsDashboard toolbox="sales" />)

    await waitFor(() => {
      expect(screen.getByText('Active one')).toBeInTheDocument()
    })
    expect(screen.queryByText('Dismissed one')).not.toBeInTheDocument()

    // Toggle to archive
    await userEvent.click(screen.getByText('View Archive'))

    expect(screen.getByText('Dismissed one')).toBeInTheDocument()
    expect(screen.queryByText('Active one')).not.toBeInTheDocument()
    expect(screen.getByText('Archive')).toBeInTheDocument()

    // Toggle back
    await userEvent.click(screen.getByText('Back to Signals'))
    expect(screen.getByText('Active one')).toBeInTheDocument()
  })

  it('calls dismiss mutation with the new state', async () => {
    const signal = makeSignal({ state: 'active', title: 'To dismiss' })
    mockFetchTaskOutputs.mockResolvedValue([signal])

    renderWithProviders(<SignalsDashboard toolbox="sales" />)

    await waitFor(() => {
      expect(screen.getByText('To dismiss')).toBeInTheDocument()
    })

    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))

    expect(mockUpdateTaskOutputState).toHaveBeenCalledWith(signal.id, 'dismissed')
  })

  it('shows empty state when no active signals', async () => {
    mockFetchTaskOutputs.mockResolvedValue([])

    renderWithProviders(<SignalsDashboard toolbox="sales" />)

    await waitFor(() => {
      expect(screen.getByText('No active signals.')).toBeInTheDocument()
    })
  })

  it('renders correct severity labels', async () => {
    const signals = [
      makeSignal({ severity: 'high', state: 'active' }),
      makeSignal({ severity: 'medium', state: 'active' }),
      makeSignal({ severity: 'low', state: 'active' }),
    ]
    mockFetchTaskOutputs.mockResolvedValue(signals)

    renderWithProviders(<SignalsDashboard toolbox="sales" />)

    await waitFor(() => {
      expect(screen.getByText('Critical')).toBeInTheDocument()
    })
    expect(screen.getByText('Warning')).toBeInTheDocument()
    expect(screen.getByText('Optimization')).toBeInTheDocument()
  })
})
