import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import Chat from '@/components/Chat'
import ConversationSidebar from '@/components/ConversationSidebar'
import { useSidebar } from '@/contexts/sidebar-context'
import { Toolbox } from '../toolboxes'
import { queryKeys, createConversation } from '@/lib/queries'

interface LocationState {
  conversationId?: string
  initialPrompt?: string
}

export function ProductionChat() {
  const location = useLocation() as { state: LocationState | null }
  const locationState = location.state
  const [conversationId, setConversationId] = useState<string | null>(
    locationState?.conversationId ?? null
  )
  const [initialPrompt] = useState<string | null>(locationState?.initialPrompt ?? null)
  const [chatStatus, setChatStatus] = useState<string>('ready')
  const queryClient = useQueryClient()
  const { setSidebarContent } = useSidebar()

  const handleConversationUpdated = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(Toolbox.Production) })
  }, [queryClient])

  const { mutate: createNewConversation } = useMutation({
    mutationFn: () => createConversation(Toolbox.Production),
    onSuccess: (data) => {
      setConversationId(data.conversation_id)
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(Toolbox.Production) })
    },
  })

  const handleDeleteConversation = useCallback(
    (id: string) => {
      if (conversationId === id) setConversationId(null)
    },
    [conversationId]
  )

  useEffect(() => {
    setSidebarContent(
      <ConversationSidebar
        toolbox={Toolbox.Production}
        currentConversationId={conversationId}
        isCurrentBusy={chatStatus === 'submitted' || chatStatus === 'streaming'}
        onSelectConversation={setConversationId}
        onNewConversation={createNewConversation}
        onDeleteConversation={handleDeleteConversation}
      />
    )
    return () => setSidebarContent(null)
  }, [
    conversationId,
    chatStatus,
    setSidebarContent,
    createNewConversation,
    handleDeleteConversation,
  ])

  return (
    <Chat
      key={conversationId ?? 'initial'}
      conversationId={conversationId}
      toolbox={Toolbox.Production}
      initialPrompt={initialPrompt}
      onConversationIdChange={setConversationId}
      onConversationUpdated={handleConversationUpdated}
      onStatusChange={setChatStatus}
    />
  )
}
