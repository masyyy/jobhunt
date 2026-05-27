import { useChat, type UIMessage } from '@ai-sdk/react'
import { useQuery } from '@tanstack/react-query'
import type { ChatStatus } from 'ai'
import {
  DefaultChatTransport,
  lastAssistantMessageIsCompleteWithApprovalResponses,
  lastAssistantMessageIsCompleteWithToolCalls,
} from 'ai'
import { useEffect, useRef } from 'react'
import { findExternalToolRenderer } from '@/customer/externalTools'
import type { PromptKey } from '@/customer/promptKeys'
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation'
import { Message, MessageContent, MessageResponse } from '@/components/ai-elements/message'
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputHeader,
  PromptInputSubmit,
  PromptInputActionMenu,
  PromptInputActionMenuTrigger,
  PromptInputActionMenuContent,
  PromptInputActionAddAttachments,
  usePromptInputAttachments,
} from '@/components/ai-elements/prompt-input'
import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
  type ToolPart,
} from '@/components/ai-elements/tool'
import type { FileUIPart } from 'ai'
import { AlertCircle, Bot, Check, FileIcon, Loader2, PlusIcon, X, XIcon } from 'lucide-react'
import { queryKeys, fetchConversationHistory } from '@/lib/queries'

interface ChatProps {
  conversationId: string | null
  toolbox?: string
  initialPrompt?: string | null
  seedPromptKey?: PromptKey
  onConversationIdChange: (id: string) => void
  onConversationUpdated: () => void
  onStatusChange?: (status: ChatStatus) => void
}

export default function Chat({
  conversationId,
  toolbox,
  initialPrompt,
  seedPromptKey,
  onConversationIdChange,
  onConversationUpdated,
  onStatusChange,
}: ChatProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.conversationHistory(conversationId, toolbox),
    queryFn: () => fetchConversationHistory(conversationId, toolbox),
    retry: 1,
  })

  useEffect(() => {
    if (data?.conversation_id && !conversationId) {
      onConversationIdChange(data.conversation_id)
    }
  }, [data, conversationId, onConversationIdChange])

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-muted-foreground text-sm">Loading...</div>
      </div>
    )
  }

  const messages = data?.messages ?? []

  return (
    <ChatInner
      // Remount when cached history actually loads. Without this, a stale-empty
      // cache entry mounts ChatInner with empty initialMessages, and useChat
      // ignores prop changes after mount — so the conversation looks empty
      // until you navigate away and back.
      key={`${conversationId ?? 'new'}:${messages.length}`}
      conversationId={conversationId}
      initialMessages={isError || messages.length === 0 ? undefined : messages}
      toolbox={toolbox}
      initialPrompt={initialPrompt}
      seedPromptKey={seedPromptKey}
      onConversationUpdated={onConversationUpdated}
      onStatusChange={onStatusChange}
    />
  )
}

interface ChatInnerProps {
  conversationId: string | null
  toolbox?: string
  initialMessages: UIMessage[] | undefined
  initialPrompt?: string | null
  seedPromptKey?: PromptKey
  onConversationUpdated: () => void
  onStatusChange?: (status: ChatStatus) => void
}

function AttachmentPreviews() {
  const { files, remove } = usePromptInputAttachments()
  if (files.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2">
      {files.map((file) => {
        const isImage = file.mediaType.startsWith('image/')
        return (
          <div
            key={file.id}
            className="group relative flex items-center gap-2 rounded-lg border bg-background p-1.5 pr-7 text-xs"
          >
            {isImage ? (
              <img
                src={file.url}
                alt={file.filename ?? 'Attached image'}
                className="h-10 w-10 rounded object-cover"
              />
            ) : (
              <div className="flex h-10 w-10 items-center justify-center rounded bg-muted">
                <FileIcon className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
            <span className="max-w-[120px] truncate text-muted-foreground">
              {file.filename ?? 'File'}
            </span>
            <button
              type="button"
              onClick={() => remove(file.id)}
              className="absolute right-1 top-1 rounded-full p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <XIcon className="h-3 w-3" />
            </button>
          </div>
        )
      })}
    </div>
  )
}

async function openDocumentInNewTab(filePath: string): Promise<void> {
  const response = await fetch(
    `/api/documents/${filePath.split('/').map(encodeURIComponent).join('/')}`
  )
  if (!response.ok) {
    console.error('Failed to fetch document', response.status)
    return
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener,noreferrer')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

// `read_file` reports a binary file via two possible shapes — both carry
// the same `<file_path> (<details>)` identifier set in read_file/tool.py.
//
//   1. `"See file <identifier>"` string. PydanticAI auto-wraps a tool that
//      returns `BinaryContent` directly: ToolReturnPart.content becomes this
//      string, and the bytes go to a separate (filtered) user prompt.
//
//   2. `{ kind: "binary", media_type, identifier }` object/JSON-string. Our
//      adapter (`_strip_binary` / `_sanitize_messages_for_ui` in
//      vercel_adapter.py) emits this when binary lives inside the tool
//      return content directly — defense-in-depth for future tools.
const READ_FILE_PREFIX = 'See file '

function splitIdentifier(identifier: string): { filePath: string; suffix: string } | null {
  const trimmed = identifier.trim()
  if (!trimmed) return null
  const parenIdx = trimmed.indexOf(' (')
  if (parenIdx === -1) return { filePath: trimmed, suffix: '' }
  return { filePath: trimmed.slice(0, parenIdx), suffix: trimmed.slice(parenIdx + 1) }
}

function parseReadFileOutput(output: unknown): { filePath: string; suffix: string } | null {
  if (typeof output === 'string') {
    if (output.startsWith(READ_FILE_PREFIX)) {
      return splitIdentifier(output.slice(READ_FILE_PREFIX.length))
    }
    const trimmed = output.trim()
    if (trimmed.startsWith('{')) {
      try {
        return parseReadFileOutput(JSON.parse(trimmed))
      } catch {
        return null
      }
    }
    return null
  }
  if (output && typeof output === 'object') {
    const stub = output as { kind?: unknown; identifier?: unknown }
    if (stub.kind === 'binary' && typeof stub.identifier === 'string') {
      return splitIdentifier(stub.identifier)
    }
  }
  return null
}

function ReadFileFilePill({ filePath, suffix }: { filePath: string; suffix: string }) {
  const filename = filePath.split('/').pop() ?? filePath
  return (
    <button
      type="button"
      onClick={() => void openDocumentInNewTab(filePath)}
      className="flex items-center gap-2 rounded-lg border bg-muted/50 px-3 py-2 text-left text-sm hover:bg-muted"
    >
      <FileIcon className="h-4 w-4 text-muted-foreground" />
      <span className="truncate font-medium">{filename}</span>
      {suffix && <span className="truncate text-xs text-muted-foreground">{suffix}</span>}
    </button>
  )
}

function FilePart({ part }: { part: FileUIPart }) {
  const isImage = part.mediaType.startsWith('image/')
  if (isImage) {
    return (
      <img
        src={part.url}
        alt={part.filename ?? 'Attached image'}
        className="max-h-64 max-w-full rounded-lg"
      />
    )
  }
  return (
    <div className="flex items-center gap-2 rounded-lg border bg-muted/50 px-3 py-2 text-sm">
      <FileIcon className="h-4 w-4 text-muted-foreground" />
      <span className="truncate">{part.filename ?? 'File'}</span>
    </div>
  )
}

function ApprovalActions({
  approvalId,
  onRespond,
}: {
  approvalId: string
  onRespond: (input: { id: string; approved: boolean }) => void | PromiseLike<void>
}) {
  return (
    <div className="flex items-center gap-2 px-4 py-3">
      <button
        type="button"
        onClick={() => void onRespond({ id: approvalId, approved: true })}
        className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-on-primary hover:bg-primary/90 transition-colors"
      >
        <Check className="h-3.5 w-3.5" />
        Approve
      </button>
      <button
        type="button"
        onClick={() => void onRespond({ id: approvalId, approved: false })}
        className="inline-flex items-center gap-1.5 rounded-md border border-outline-variant bg-background px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors"
      >
        <X className="h-3.5 w-3.5" />
        Deny
      </button>
    </div>
  )
}

function ChatInner({
  conversationId,
  toolbox,
  initialMessages,
  initialPrompt,
  seedPromptKey,
  onConversationUpdated,
  onStatusChange,
}: ChatInnerProps) {
  // Tracks whether the seed prompt still needs to be sent to the backend.
  // Flipped after the first send so subsequent turns carry normal user text.
  const seedPendingRef = useRef<boolean>(
    Boolean(seedPromptKey) && (initialMessages?.length ?? 0) === 0
  )

  const chatOptions: Parameters<typeof useChat>[0] = {
    messages: initialMessages,
    // Auto-resume the agent run when the user has either approved/denied a
    // gated tool (HITL approval) or supplied a result for an external tool
    // (e.g. a multi-choice answer). Both flavours land the BE in the same
    // `DeferredToolResults` resume path.
    sendAutomaticallyWhen: (state) =>
      lastAssistantMessageIsCompleteWithApprovalResponses(state) ||
      lastAssistantMessageIsCompleteWithToolCalls(state),
    transport: new DefaultChatTransport({
      api: '/api/chat',
      headers: () => {
        const h: Record<string, string> = {}
        if (conversationId) h['x-conversation-id'] = conversationId
        if (toolbox) h['x-toolbox'] = toolbox
        return h
      },
      // Send only the last message — the backend loads prior history from the DB.
      // This avoids duplicate message history (frontend + DB) being sent to the LLM.
      // On a seeded first turn the backend ignores the user message and
      // substitutes the stored seed prompt, so we send `messages: []`.
      prepareSendMessagesRequest({ id, messages, trigger }) {
        // PromptKey resolves to `never` in the template (empty registry), so
        // the second clause always narrows to falsy until a fork adds a key.
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
        if (seedPendingRef.current && seedPromptKey) {
          seedPendingRef.current = false
          return {
            body: {
              id,
              messages: [],
              trigger,
              prompt_key: seedPromptKey,
            },
          }
        }
        return {
          body: {
            id,
            messages: [messages[messages.length - 1]],
            trigger,
          },
        }
      },
    }),
    onFinish: () => {
      onConversationUpdated()
    },
  }
  // Scope useChat's internal message store per conversation or per toolbox.
  // Without an explicit id, useChat uses a shared default store, which leaks
  // messages across toolbox navigations.
  chatOptions.id = conversationId ?? `new-${toolbox ?? 'default'}`

  const { messages, sendMessage, status, stop, error, addToolApprovalResponse, addToolOutput } =
    useChat(chatOptions)

  // Show a "Thinking..." indicator whenever the server has work in flight
  // but nothing is currently rendering — either before the first chunk
  // (`submitted`) or while the model is digesting a tool result mid-stream
  // (last visible part is a completed tool call, no text streaming yet).
  const showPendingIndicator = (() => {
    if (status === 'submitted') return true
    if (status !== 'streaming') return false
    const last = messages[messages.length - 1]
    if (last.role !== 'assistant') return true
    const lastPart = last.parts[last.parts.length - 1]
    if (lastPart.type.startsWith('tool-') || lastPart.type === 'dynamic-tool') {
      const toolPart = lastPart as ToolPart
      return toolPart.state === 'output-available' || toolPart.state === 'output-error'
    }
    return false
  })()

  useEffect(() => {
    onStatusChange?.(status)
  }, [status, onStatusChange])

  const promptSentRef = useRef(false)
  useEffect(() => {
    if (initialPrompt && !promptSentRef.current) {
      promptSentRef.current = true
      void sendMessage({ text: initialPrompt })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex flex-1 flex-col min-h-0">
      <Conversation className="flex-1">
        {messages.length === 0 ? (
          <ConversationEmptyState className="px-4 py-8">
            <div className="flex flex-col items-center gap-3 text-center">
              <div className="text-muted-foreground/40">
                <Bot className="h-12 w-12" />
              </div>
              <h3 className="font-headline font-semibold text-sm text-muted-foreground">
                What can I help with?
              </h3>
            </div>
          </ConversationEmptyState>
        ) : (
          <ConversationContent className="max-w-4xl mx-auto w-full px-4">
            {messages.map((message) => (
              <Message key={message.id} from={message.role}>
                <MessageContent>
                  {message.parts.map((part, i) => {
                    if (part.type === 'text') {
                      if (message.role === 'user') {
                        return <span key={`${message.id}-${i}`}>{part.text}</span>
                      }
                      return (
                        <MessageResponse key={`${message.id}-${i}`}>{part.text}</MessageResponse>
                      )
                    }

                    // Handle tool calls - check for tool UI parts
                    if (part.type.startsWith('tool-') || part.type === 'dynamic-tool') {
                      const toolPart = part as ToolPart
                      const toolName =
                        toolPart.type === 'dynamic-tool'
                          ? toolPart.toolName
                          : toolPart.type.replace('tool-', '')

                      // External (FE-executed) tool — render the customer
                      // component for the prompt UI; supply the answer back
                      // via addToolOutput so the BE can resume the agent run.
                      const ExternalRenderer = findExternalToolRenderer(toolName)
                      if (ExternalRenderer) {
                        return (
                          <Tool key={`${message.id}-${i}`}>
                            <ToolHeader
                              type={toolPart.type as `tool-${string}`}
                              state={toolPart.state}
                              title={toolName}
                            />
                            <ToolContent>
                              <ToolInput input={toolPart.input} />
                              {toolPart.state === 'input-available' ? (
                                <ExternalRenderer
                                  toolCallId={toolPart.toolCallId}
                                  input={toolPart.input}
                                  onResult={(output) =>
                                    void addToolOutput({
                                      tool: toolName,
                                      toolCallId: toolPart.toolCallId,
                                      output,
                                    })
                                  }
                                />
                              ) : (
                                <ToolOutput
                                  output={toolPart.output}
                                  errorText={toolPart.errorText}
                                />
                              )}
                            </ToolContent>
                          </Tool>
                        )
                      }

                      // Handle the discriminated union type properly
                      if (toolPart.type === 'dynamic-tool') {
                        const readFile =
                          toolPart.toolName === 'read_file'
                            ? parseReadFileOutput(toolPart.output)
                            : null
                        return (
                          <Tool key={`${message.id}-${i}`}>
                            <ToolHeader
                              type="dynamic-tool"
                              state={toolPart.state}
                              toolName={toolPart.toolName}
                              title={toolName}
                            />
                            <ToolContent>
                              <ToolInput input={toolPart.input} />
                              {toolPart.state === 'approval-requested' && (
                                <ApprovalActions
                                  approvalId={toolPart.approval.id}
                                  onRespond={addToolApprovalResponse}
                                />
                              )}
                              {readFile ? (
                                <div className="px-4 py-3">
                                  <ReadFileFilePill
                                    filePath={readFile.filePath}
                                    suffix={readFile.suffix}
                                  />
                                </div>
                              ) : (
                                <ToolOutput
                                  output={toolPart.output}
                                  errorText={toolPart.errorText}
                                />
                              )}
                            </ToolContent>
                          </Tool>
                        )
                      }

                      const readFile =
                        toolPart.type === 'tool-read_file'
                          ? parseReadFileOutput(toolPart.output)
                          : null

                      return (
                        <Tool key={`${message.id}-${i}`}>
                          <ToolHeader
                            type={toolPart.type}
                            state={toolPart.state}
                            title={toolName}
                          />
                          <ToolContent>
                            <ToolInput input={toolPart.input} />
                            {toolPart.state === 'approval-requested' && (
                              <ApprovalActions
                                approvalId={toolPart.approval.id}
                                onRespond={addToolApprovalResponse}
                              />
                            )}
                            {readFile ? (
                              <div className="px-4 py-3">
                                <ReadFileFilePill
                                  filePath={readFile.filePath}
                                  suffix={readFile.suffix}
                                />
                              </div>
                            ) : (
                              <ToolOutput output={toolPart.output} errorText={toolPart.errorText} />
                            )}
                          </ToolContent>
                        </Tool>
                      )
                    }

                    if (part.type === 'file') {
                      return <FilePart key={`${message.id}-${i}`} part={part} />
                    }

                    return null
                  })}
                </MessageContent>
              </Message>
            ))}
            {showPendingIndicator && (
              <Message from="assistant">
                <MessageContent>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm">Thinking...</span>
                  </div>
                </MessageContent>
              </Message>
            )}
            {error && status === 'ready' && (
              <Message from="assistant">
                <MessageContent>
                  <div className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-4 w-4 flex-shrink-0" />
                    <span className="text-sm">Something went wrong. Please try again.</span>
                  </div>
                </MessageContent>
              </Message>
            )}
          </ConversationContent>
        )}
        <ConversationScrollButton />
      </Conversation>

      <div className="flex-shrink-0 pb-4 pt-2 px-4">
        <div className="max-w-5xl mx-auto w-full">
          <PromptInput
            className="[&_[data-slot=input-group]]:border-primary/40 [&_[data-slot=input-group]]:shadow-[0_0_16px_-2px_rgba(255,193,131,0.2)] [&_[data-slot=input-group]]:bg-surface-container-low"
            onSubmit={(message) => {
              if (message.text.trim() || message.files.length > 0) {
                void sendMessage({ text: message.text, files: message.files })
              }
            }}
            globalDrop
            accept="image/png,image/jpeg,image/webp,image/gif,application/pdf,text/csv"
            maxFiles={10}
            maxFileSize={20 * 1024 * 1024}
          >
            <PromptInputHeader>
              <AttachmentPreviews />
            </PromptInputHeader>
            <PromptInputTextarea
              placeholder="How can I help?"
              className="placeholder:text-muted-foreground/50 focus:placeholder:text-transparent"
            />
            <PromptInputFooter>
              <PromptInputActionMenu>
                <PromptInputActionMenuTrigger>
                  <PlusIcon />
                </PromptInputActionMenuTrigger>
                <PromptInputActionMenuContent>
                  <PromptInputActionAddAttachments />
                </PromptInputActionMenuContent>
              </PromptInputActionMenu>
              <PromptInputSubmit status={status} onStop={stop} />
            </PromptInputFooter>
          </PromptInput>
        </div>
      </div>
    </div>
  )
}
