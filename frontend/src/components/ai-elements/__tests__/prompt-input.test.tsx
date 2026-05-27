import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputSubmit,
  PromptInputFooter,
  PromptInputProvider,
  usePromptInputController,
  usePromptInputAttachments,
} from '../prompt-input'

function createFile(name: string, type: string, size = 100): File {
  const content = new Uint8Array(size)
  return new File([content], name, { type })
}

/** Minimal PromptInput with textarea + submit wired up. */
function SimplePromptInput({
  onSubmit = vi.fn(),
  onError,
  status,
  ...rest
}: {
  onSubmit?: (msg: { text: string; files: unknown[] }) => void
  onError?: (err: { code: string; message: string }) => void
  status?: 'ready' | 'submitted' | 'streaming' | 'error'
  accept?: string
  maxFiles?: number
  maxFileSize?: number
}) {
  return (
    <PromptInput onSubmit={onSubmit} onError={onError} {...rest}>
      <PromptInputTextarea />
      <PromptInputFooter>
        <PromptInputSubmit status={status} />
      </PromptInputFooter>
    </PromptInput>
  )
}

describe('PromptInput', () => {
  describe('form submission', () => {
    it('submits text via form submit', async () => {
      const onSubmit = vi.fn()
      render(<SimplePromptInput onSubmit={onSubmit} />)

      const textarea = screen.getByRole('textbox')
      await userEvent.type(textarea, 'Hello world')
      const form = textarea.closest('form')
      if (!form) throw new Error('form not found')
      fireEvent.submit(form)

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({ text: 'Hello world' }),
          expect.anything()
        )
      })
    })

    it('Enter key submits, Shift+Enter does not', async () => {
      const onSubmit = vi.fn()
      render(<SimplePromptInput onSubmit={onSubmit} />)

      const textarea = screen.getByRole('textbox')
      await userEvent.type(textarea, 'test message')

      // Shift+Enter should NOT submit
      await userEvent.keyboard('{Shift>}{Enter}{/Shift}')
      expect(onSubmit).not.toHaveBeenCalled()

      // Enter should submit
      await userEvent.keyboard('{Enter}')
      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalled()
      })
    })

    it('Enter does not submit when submit button is disabled', async () => {
      const onSubmit = vi.fn()
      render(
        <PromptInput onSubmit={onSubmit}>
          <PromptInputTextarea />
          <PromptInputFooter>
            <PromptInputSubmit status="ready" disabled />
          </PromptInputFooter>
        </PromptInput>
      )

      const textarea = screen.getByRole('textbox')
      await userEvent.type(textarea, 'test')
      await userEvent.keyboard('{Enter}')

      expect(onSubmit).not.toHaveBeenCalled()
    })
  })

  describe('file validation', () => {
    it('rejects files that do not match accept filter', () => {
      const onError = vi.fn()
      render(<SimplePromptInput accept="image/*" onError={onError} />)

      const fileInput = screen.getByLabelText('Upload files')
      const txtFile = createFile('doc.txt', 'text/plain')

      fireEvent.change(fileInput, { target: { files: [txtFile] } })

      expect(onError).toHaveBeenCalledWith(expect.objectContaining({ code: 'accept' }))
    })

    it('enforces maxFiles cap', () => {
      const onError = vi.fn()
      render(<SimplePromptInput maxFiles={1} onError={onError} />)

      const fileInput = screen.getByLabelText('Upload files')
      const files = [createFile('a.png', 'image/png'), createFile('b.png', 'image/png')]

      fireEvent.change(fileInput, { target: { files } })

      expect(onError).toHaveBeenCalledWith(expect.objectContaining({ code: 'max_files' }))
    })

    it('enforces maxFileSize', () => {
      const onError = vi.fn()
      render(<SimplePromptInput maxFileSize={50} onError={onError} />)

      const fileInput = screen.getByLabelText('Upload files')
      const bigFile = createFile('big.png', 'image/png', 200)

      fireEvent.change(fileInput, { target: { files: [bigFile] } })

      expect(onError).toHaveBeenCalledWith(expect.objectContaining({ code: 'max_file_size' }))
    })
  })

  describe('attachment management', () => {
    it('Backspace removes last attachment when textarea is empty', async () => {
      /** Renders attachment count for assertion. */
      function AttachmentCount() {
        const { files } = usePromptInputAttachments()
        return <span data-testid="count">{files.length}</span>
      }

      render(
        <PromptInput onSubmit={vi.fn()}>
          <PromptInputTextarea />
          <AttachmentCount />
          <PromptInputSubmit />
        </PromptInput>
      )

      // Add a file
      const fileInput = screen.getByLabelText('Upload files')
      fireEvent.change(fileInput, {
        target: { files: [createFile('a.png', 'image/png')] },
      })

      expect(screen.getByTestId('count')).toHaveTextContent('1')

      // Press Backspace with empty textarea
      const textarea = screen.getByRole('textbox')
      await userEvent.click(textarea)
      await userEvent.keyboard('{Backspace}')

      expect(screen.getByTestId('count')).toHaveTextContent('0')
    })
  })

  describe('submit button states', () => {
    it('shows Submit label when ready, Stop when generating', () => {
      const { rerender } = render(<SimplePromptInput status="ready" />)
      expect(screen.getByRole('button', { name: 'Submit' })).toBeInTheDocument()

      rerender(<SimplePromptInput status="streaming" />)
      expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()

      rerender(<SimplePromptInput status="submitted" />)
      expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
    })

    it('calls onStop instead of submit when streaming', async () => {
      const onSubmit = vi.fn()
      const onStop = vi.fn()
      render(
        <PromptInput onSubmit={onSubmit}>
          <PromptInputTextarea />
          <PromptInputSubmit status="streaming" onStop={onStop} />
        </PromptInput>
      )

      await userEvent.click(screen.getByRole('button', { name: 'Stop' }))
      expect(onStop).toHaveBeenCalled()
      expect(onSubmit).not.toHaveBeenCalled()
    })
  })

  describe('PromptInputProvider', () => {
    it('lifts text state outside PromptInput', async () => {
      function TextDisplay() {
        const { textInput } = usePromptInputController()
        return <span data-testid="external-text">{textInput.value}</span>
      }

      render(
        <PromptInputProvider>
          <TextDisplay />
          <PromptInput onSubmit={vi.fn()}>
            <PromptInputTextarea />
            <PromptInputSubmit />
          </PromptInput>
        </PromptInputProvider>
      )

      const textarea = screen.getByRole('textbox')
      await userEvent.type(textarea, 'shared state')

      expect(screen.getByTestId('external-text')).toHaveTextContent('shared state')
    })
  })
})
