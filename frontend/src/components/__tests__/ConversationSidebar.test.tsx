import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '@/test/helpers'
import type { ConversationItem } from '@/lib/queries'

// Mock AppSidebar — renders children directly
vi.mock('@/components/AppSidebar', () => ({
  default: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="sidebar">{children}</div>
  ),
}))

// Mock queries
const mockFetchConversations = vi.fn<() => Promise<ConversationItem[]>>()
const mockDeleteConversation = vi.fn<(id: string) => Promise<void>>()

vi.mock('@/lib/queries', async (importOriginal) => {
  return {
    ...(await importOriginal()),
    fetchConversations: (...args: unknown[]) => mockFetchConversations(...(args as [])),
    deleteConversation: (...args: unknown[]) => mockDeleteConversation(...(args as [string])),
  }
})

import ConversationSidebar from '../ConversationSidebar'

function makeConversation(overrides: Partial<ConversationItem> = {}): ConversationItem {
  return {
    conversation_id: crypto.randomUUID(),
    title: 'Test conversation',
    updated_at: new Date().toISOString(),
    ...overrides,
  }
}

describe('ConversationSidebar', () => {
  const defaultProps = {
    currentConversationId: null,
    isCurrentBusy: false,
    toolbox: 'sales',
    onToolboxChange: vi.fn(),
    onSelectConversation: vi.fn(),
    onNewConversation: vi.fn(),
    onDeleteConversation: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockDeleteConversation.mockResolvedValue(undefined)
  })

  it('renders conversation list from fetched data', async () => {
    const conversations = [
      makeConversation({ title: 'Revenue analysis' }),
      makeConversation({ title: 'Pipeline review' }),
    ]
    mockFetchConversations.mockResolvedValue(conversations)

    renderWithProviders(<ConversationSidebar {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Revenue analysis')).toBeInTheDocument()
    })
    expect(screen.getByText('Pipeline review')).toBeInTheDocument()
  })

  it('shows empty state when no conversations exist', async () => {
    mockFetchConversations.mockResolvedValue([])

    renderWithProviders(<ConversationSidebar {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('No conversations yet')).toBeInTheDocument()
    })
  })

  it('calls onSelectConversation when clicking a conversation', async () => {
    const user = userEvent.setup()
    const conv = makeConversation({ title: 'Click me' })
    mockFetchConversations.mockResolvedValue([conv])

    renderWithProviders(<ConversationSidebar {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Click me')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Click me'))
    expect(defaultProps.onSelectConversation).toHaveBeenCalledWith(conv.conversation_id)
  })

  it('calls onNewConversation when clicking the new conversation button', async () => {
    const user = userEvent.setup()
    mockFetchConversations.mockResolvedValue([])

    renderWithProviders(<ConversationSidebar {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByLabelText('New conversation')).toBeInTheDocument()
    })

    await user.click(screen.getByLabelText('New conversation'))
    expect(defaultProps.onNewConversation).toHaveBeenCalledTimes(1)
  })

  it('highlights the currently selected conversation', async () => {
    const conv = makeConversation({ title: 'Selected one' })
    mockFetchConversations.mockResolvedValue([conv])

    renderWithProviders(
      <ConversationSidebar {...defaultProps} currentConversationId={conv.conversation_id} />
    )

    await waitFor(() => {
      expect(screen.getByText('Selected one')).toBeInTheDocument()
    })

    const button = screen.getByText('Selected one').closest('button')
    expect(button?.className).toContain('border-primary')
  })

  it('triggers delete via context menu and calls onDeleteConversation', async () => {
    const user = userEvent.setup()
    const conv = makeConversation({ title: 'Delete me' })
    mockFetchConversations.mockResolvedValue([conv])

    renderWithProviders(<ConversationSidebar {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText('Delete me')).toBeInTheDocument()
    })

    // Radix ContextMenu requires a contextmenu event (not just right-click pointer)
    const target = screen.getByText('Delete me')
    await user.pointer({ target, keys: '[MouseRight]' })
    // Also fire contextmenu event explicitly for Radix
    target.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true }))

    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: /delete/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('menuitem', { name: /delete/i }))

    await waitFor(() => {
      expect(mockDeleteConversation).toHaveBeenCalled()
    })
    expect(mockDeleteConversation.mock.calls[0][0]).toBe(conv.conversation_id)
  })

  it('disables delete for the active conversation when busy', async () => {
    const user = userEvent.setup()
    const conv = makeConversation({ title: 'Busy conv' })
    mockFetchConversations.mockResolvedValue([conv])

    renderWithProviders(
      <ConversationSidebar
        {...defaultProps}
        currentConversationId={conv.conversation_id}
        isCurrentBusy={true}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Busy conv')).toBeInTheDocument()
    })

    // Open context menu
    const target = screen.getByText('Busy conv')
    await user.pointer({ target, keys: '[MouseRight]' })
    target.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true }))

    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: /delete/i })).toBeInTheDocument()
    })

    // The delete menu item should be disabled
    const deleteItem = screen.getByRole('menuitem', { name: /delete/i })
    expect(deleteItem).toHaveAttribute('data-disabled')
  })
})
