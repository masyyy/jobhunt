import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { UIMessage } from '@ai-sdk/react'
import { renderWithProviders } from '@/test/helpers'

// --- Mocks ---

// Mock AppSidebar (transitive dep via ConversationSidebar if imported)
vi.mock('@/components/AppSidebar', () => ({
  default: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="sidebar">{children}</div>
  ),
}))

// Track useChat calls and expose controls
const mockSendMessage = vi.fn()
const mockStop = vi.fn()
let useChatStatus = 'ready'
let useChatMessages: UIMessage[] = []
let capturedOnFinish: (() => void) | undefined
let capturedChatOptions: Record<string, unknown> | undefined

vi.mock('@ai-sdk/react', () => ({
  useChat: (options: Record<string, unknown>) => {
    capturedChatOptions = options
    capturedOnFinish = options.onFinish as (() => void) | undefined
    return {
      messages: useChatMessages,
      sendMessage: mockSendMessage,
      status: useChatStatus,
      stop: mockStop,
    }
  },
}))

// Mock transport — needs to be a real class since it's used with `new`
vi.mock('ai', () => ({
  DefaultChatTransport: class MockTransport {
    options: Record<string, unknown>
    constructor(options: Record<string, unknown>) {
      this.options = options
    }
  },
}))

// Mock queries
const mockFetchConversationHistory =
  vi.fn<(id: string | null) => Promise<{ conversation_id: string | null; messages: UIMessage[] }>>()

vi.mock('@/lib/queries', async (importOriginal) => {
  return {
    ...(await importOriginal()),
    fetchConversationHistory: (...args: unknown[]) =>
      mockFetchConversationHistory(...(args as [string | null])),
  }
})

vi.mock('@/lib/api', () => ({
  getAuthToken: () => Promise.resolve('test-token'),
  authFetch: vi.fn(),
}))

import Chat from '../Chat'

function makeMessage(overrides: Partial<UIMessage> = {}): UIMessage {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    parts: [{ type: 'text' as const, text: 'Hello from the assistant' }],
    ...overrides,
  } as UIMessage
}

describe('Chat', () => {
  const defaultProps = {
    conversationId: 'conv-123',
    initialPrompt: null,
    onConversationIdChange: vi.fn(),
    onConversationUpdated: vi.fn(),
    onStatusChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    useChatStatus = 'ready'
    useChatMessages = []
    capturedOnFinish = undefined
    capturedChatOptions = undefined
  })

  it('shows loading state while fetching conversation history', () => {
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    mockFetchConversationHistory.mockReturnValue(new Promise(() => {}))

    renderWithProviders(<Chat {...defaultProps} />)

    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('renders empty state when no messages exist', async () => {
    mockFetchConversationHistory.mockResolvedValue({
      conversation_id: 'conv-123',
      messages: [],
    })

    renderWithProviders(<Chat {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('What can I help with?')).toBeInTheDocument()
    })
  })

  it('renders prior messages from conversation history', async () => {
    const messages = [
      makeMessage({ role: 'user', parts: [{ type: 'text' as const, text: 'Hi there' }] }),
      makeMessage({
        role: 'assistant',
        parts: [{ type: 'text' as const, text: 'Hello! How can I help?' }],
      }),
    ]
    mockFetchConversationHistory.mockResolvedValue({
      conversation_id: 'conv-123',
      messages,
    })
    useChatMessages = messages

    renderWithProviders(<Chat {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Hi there')).toBeInTheDocument()
    })
    expect(screen.getByText('Hello! How can I help?')).toBeInTheDocument()
  })

  it('shows "Thinking..." spinner when status is submitted', async () => {
    mockFetchConversationHistory.mockResolvedValue({
      conversation_id: 'conv-123',
      messages: [],
    })
    useChatStatus = 'submitted'
    useChatMessages = [
      makeMessage({ role: 'user', parts: [{ type: 'text' as const, text: 'Test' }] }),
    ]

    renderWithProviders(<Chat {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Thinking...')).toBeInTheDocument()
    })
  })

  it('calls onConversationUpdated when onFinish fires', async () => {
    mockFetchConversationHistory.mockResolvedValue({
      conversation_id: 'conv-123',
      messages: [],
    })

    renderWithProviders(<Chat {...defaultProps} />)

    await waitFor(() => {
      expect(capturedOnFinish).toBeDefined()
    })

    capturedOnFinish?.()
    expect(defaultProps.onConversationUpdated).toHaveBeenCalled()
  })

  it('reports status changes via onStatusChange', async () => {
    mockFetchConversationHistory.mockResolvedValue({
      conversation_id: 'conv-123',
      messages: [],
    })

    renderWithProviders(<Chat {...defaultProps} />)

    await waitFor(() => {
      expect(defaultProps.onStatusChange).toHaveBeenCalledWith('ready')
    })
  })

  it('auto-sends initialPrompt exactly once on mount', async () => {
    mockFetchConversationHistory.mockResolvedValue({
      conversation_id: 'conv-123',
      messages: [],
    })

    renderWithProviders(<Chat {...defaultProps} initialPrompt="Analyze revenue drop" />)

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledWith({ text: 'Analyze revenue drop' })
    })
    expect(mockSendMessage).toHaveBeenCalledTimes(1)
  })

  it('does not auto-send when initialPrompt is null', async () => {
    mockFetchConversationHistory.mockResolvedValue({
      conversation_id: 'conv-123',
      messages: [],
    })

    renderWithProviders(<Chat {...defaultProps} initialPrompt={null} />)

    await waitFor(() => {
      expect(screen.getByText('What can I help with?')).toBeInTheDocument()
    })
    expect(mockSendMessage).not.toHaveBeenCalled()
  })

  it('passes conversation id to useChat and transport headers', async () => {
    mockFetchConversationHistory.mockResolvedValue({
      conversation_id: 'conv-123',
      messages: [],
    })

    renderWithProviders(<Chat {...defaultProps} />)

    await waitFor(() => {
      expect(capturedChatOptions).toBeDefined()
    })
    expect(capturedChatOptions?.id).toBe('conv-123')
  })

  it('submits user message via prompt input', async () => {
    const user = userEvent.setup()
    mockFetchConversationHistory.mockResolvedValue({
      conversation_id: 'conv-123',
      messages: [],
    })

    renderWithProviders(<Chat {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText('How can I help?')).toBeInTheDocument()
    })

    const textarea = screen.getByPlaceholderText('How can I help?')
    await user.type(textarea, 'Hello world')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalled()
    })
  })
})
