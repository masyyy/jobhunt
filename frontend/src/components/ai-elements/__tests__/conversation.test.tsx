import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Conversation, ConversationEmptyState, ConversationScrollButton } from '../conversation'

describe('Conversation', () => {
  it('has role="log" for assistive technology', () => {
    render(<Conversation>content</Conversation>)
    expect(screen.getByRole('log')).toBeInTheDocument()
  })
})

describe('ConversationEmptyState', () => {
  it('renders default title as h2 and description when no children', () => {
    render(<ConversationEmptyState />)
    const heading = screen.getByText('No messages yet')
    expect(heading.tagName).toBe('H2')
    expect(screen.getByText('Start a conversation to see messages here')).toBeInTheDocument()
  })

  it('renders custom title and description', () => {
    render(<ConversationEmptyState title="Custom" description="Custom desc" />)
    expect(screen.getByText('Custom')).toBeInTheDocument()
    expect(screen.getByText('Custom desc')).toBeInTheDocument()
  })

  it('renders children instead of defaults when provided', () => {
    render(
      <ConversationEmptyState title="Should not appear">
        <span>Custom child</span>
      </ConversationEmptyState>
    )
    expect(screen.getByText('Custom child')).toBeInTheDocument()
    expect(screen.queryByText('Should not appear')).not.toBeInTheDocument()
  })
})

describe('ConversationScrollButton', () => {
  it('does not render when at bottom', () => {
    // Default mock has isAtBottom: true
    const { container } = render(<ConversationScrollButton />)
    expect(container.querySelector('button')).toBeNull()
  })

  it('renders and calls scrollToBottom when not at bottom', async () => {
    const scrollToBottom = vi.fn()

    // Override the mock for this test
    const stb = await import('use-stick-to-bottom')
    vi.spyOn(stb, 'useStickToBottomContext').mockReturnValue({
      isAtBottom: false,
      scrollToBottom,
    } as unknown as ReturnType<typeof stb.useStickToBottomContext>)

    render(<ConversationScrollButton />)

    const button = screen.getByRole('button')
    expect(button).toBeInTheDocument()

    button.click()
    expect(scrollToBottom).toHaveBeenCalled()
  })
})
