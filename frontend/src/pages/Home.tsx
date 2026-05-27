import { useState, useCallback } from 'react'
import type { ChatStatus } from 'ai'
import { useLocation } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import Chat from '../components/Chat'
import ConversationSidebar from '../components/ConversationSidebar'
import { queryKeys, createConversation } from '@/lib/queries'

interface LocationState {
  conversationId?: string
  initialPrompt?: string
}

export default function Home() {
  const location = useLocation() as { state: LocationState | null }
  const locationState = location.state
  const [initialPrompt, setInitialPrompt] = useState(locationState?.initialPrompt ?? null)
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(
    locationState?.conversationId ?? null
  )
  const [chatStatus, setChatStatus] = useState<ChatStatus>('ready')
  const queryClient = useQueryClient()

  const handleSelectConversation = useCallback((id: string) => {
    setCurrentConversationId(id)
    setInitialPrompt(null)
  }, [])

  const newConversationMutation = useMutation({
    mutationFn: createConversation,
    onSuccess: (data) => {
      setCurrentConversationId(data.conversation_id)
      setInitialPrompt(null)
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations() })
    },
  })

  const handleNewConversation = useCallback(() => {
    newConversationMutation.mutate(undefined)
  }, [newConversationMutation])

  const handleDeleteConversation = useCallback(
    (id: string) => {
      if (currentConversationId === id) {
        setCurrentConversationId(null)
      }
    },
    [currentConversationId]
  )

  const handleConversationUpdated = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.conversations() })
  }, [queryClient])

  return (
    <div className="h-dvh bg-background flex flex-col md:flex-row overflow-hidden w-full">
      <ConversationSidebar
        currentConversationId={currentConversationId}
        isCurrentBusy={chatStatus === 'submitted' || chatStatus === 'streaming'}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
      />
      <div className="flex-1 flex flex-col min-h-0">
        <main className="flex-1 flex flex-col min-h-0">
          <Chat
            key={currentConversationId ?? 'initial'}
            conversationId={currentConversationId}
            initialPrompt={initialPrompt}
            onConversationIdChange={setCurrentConversationId}
            onConversationUpdated={handleConversationUpdated}
            onStatusChange={setChatStatus}
          />
        </main>
      </div>
    </div>
  )
}
