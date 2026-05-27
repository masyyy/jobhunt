import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { queryKeys, fetchConversations, deleteConversation } from '@/lib/queries'
import { cn, formatRelativeTime } from '@/lib/utils'

interface ConversationSidebarProps {
  toolbox?: string
  currentConversationId: string | null
  isCurrentBusy?: boolean
  onSelectConversation: (id: string) => void
  onNewConversation: () => void
  onDeleteConversation?: (id: string) => void
}

export default function ConversationSidebar({
  toolbox,
  currentConversationId,
  isCurrentBusy = false,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
}: ConversationSidebarProps) {
  const queryClient = useQueryClient()

  const { data: conversations = [] } = useQuery({
    queryKey: queryKeys.conversations(toolbox),
    queryFn: () => fetchConversations(toolbox),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteConversation,
    onSuccess: (_data, deletedId) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.conversations(toolbox) })
      onDeleteConversation?.(deletedId)
    },
  })

  return (
    <div className="flex flex-col">
      {/* Recent Queries header */}
      <div className="flex items-center justify-between px-4 mt-4 mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          Recent Queries
        </span>
        <button
          onClick={onNewConversation}
          className="h-5 w-5 flex items-center justify-center rounded-full border border-outline-variant text-muted-foreground hover:text-foreground hover:border-primary transition-colors"
          aria-label="New conversation"
        >
          <Plus className="h-3 w-3" />
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-3">
        <div className="flex flex-col gap-0.5">
          {conversations.map((conv) => (
            <ContextMenu key={conv.conversation_id}>
              <ContextMenuTrigger asChild>
                <button
                  className={cn(
                    'w-full text-left px-3 py-2.5 rounded-[0.25rem] transition-colors group',
                    conv.conversation_id === currentConversationId
                      ? 'bg-surface-container-high text-foreground border-l-2 border-primary'
                      : 'text-foreground/80 hover:bg-accent'
                  )}
                  onClick={() => onSelectConversation(conv.conversation_id)}
                >
                  <div className="text-sm truncate font-medium">{conv.title}</div>
                  <div className="text-[10px] text-muted-foreground font-mono mt-0.5">
                    {formatRelativeTime(conv.updated_at)}
                  </div>
                </button>
              </ContextMenuTrigger>
              <ContextMenuContent>
                <ContextMenuItem
                  className="text-destructive focus:text-destructive"
                  disabled={isCurrentBusy && conv.conversation_id === currentConversationId}
                  onSelect={() => deleteMutation.mutate(conv.conversation_id)}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </ContextMenuItem>
              </ContextMenuContent>
            </ContextMenu>
          ))}
          {conversations.length === 0 && (
            <p className="text-muted-foreground px-3 py-4 text-xs text-center">
              No conversations yet
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
