import type { UIMessage } from '@ai-sdk/react'
import { authFetch } from '@/lib/api'

export interface ConversationItem {
  conversation_id: string
  title: string
  updated_at: string
}

export interface ConversationHistory {
  conversation_id: string | null
  messages: UIMessage[]
}

export interface ConversationCreateResponse {
  conversation_id: string
}

export interface TaskOutput {
  id: string
  task_name: string
  toolbox: string | null
  payload: Record<string, unknown>
  created_at: string
}

// Signal-specific payload shape for the "generate-signals" task.
// Lives here because the frontend renderer needs to type-narrow payload.
export type SignalSeverity = 'high' | 'medium' | 'low'
export type SignalState = 'active' | 'dismissed' | 'acted_on' | 'expired'

export interface SignalPayload {
  title: string
  prompt: string
  severity: SignalSeverity
  category: string
  state: SignalState
  source?: string
}

export type DashboardQueryParams = Record<string, string | number>

export const queryKeys = {
  conversations: (toolbox?: string) => ['conversations', toolbox] as const,
  conversationHistory: (id: string | null, toolbox?: string) =>
    ['conversationHistory', id, toolbox] as const,
  taskOutputs: (taskName: string, toolbox?: string) => ['taskOutputs', taskName, toolbox] as const,
  dashboardQuery: (queryName: string, params?: DashboardQueryParams) =>
    ['dashboardQuery', queryName, params ?? null] as const,
  adminUsers: () => ['adminUsers'] as const,
}

export interface AdminUser {
  id: string
  email: string
  role: 'admin' | 'regular'
  created_at: string
  last_seen_at: string
}

export interface InviteResponse {
  email: string
  action_link: string
}

export async function fetchConversations(toolbox?: string): Promise<ConversationItem[]> {
  const params = new URLSearchParams()
  if (toolbox) params.set('toolbox', toolbox)
  const qs = params.toString()
  const url = qs ? `/api/conversations?${qs}` : '/api/conversations'
  const response = await authFetch(url)
  if (!response.ok) {
    throw new Error('Failed to load conversations')
  }
  return response.json() as Promise<ConversationItem[]>
}

export async function fetchConversationHistory(
  conversationId: string | null,
  toolbox?: string
): Promise<ConversationHistory> {
  let url: string
  if (conversationId) {
    url = `/api/conversation/${conversationId}/history`
  } else {
    const params = new URLSearchParams()
    if (toolbox) params.set('toolbox', toolbox)
    const qs = params.toString()
    url = `/api/conversation/history${qs ? `?${qs}` : ''}`
  }
  const response = await authFetch(url)
  if (!response.ok) {
    throw new Error('Failed to load conversation history')
  }
  return response.json() as Promise<ConversationHistory>
}

export async function fetchTaskOutputs(taskName: string, toolbox?: string): Promise<TaskOutput[]> {
  const params = new URLSearchParams()
  params.set('task_name', taskName)
  if (toolbox) {
    params.set('toolbox', toolbox)
  }
  const response = await authFetch(`/api/task-outputs?${params.toString()}`)
  if (!response.ok) {
    throw new Error('Failed to load task outputs')
  }
  return response.json() as Promise<TaskOutput[]>
}

export async function updateTaskOutputState(
  outputId: string,
  state: SignalState
): Promise<TaskOutput> {
  const response = await authFetch(`/api/task-outputs/${outputId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state }),
  })
  if (!response.ok) {
    throw new Error('Failed to update task output state')
  }
  return response.json() as Promise<TaskOutput>
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await authFetch(`/api/conversation/${conversationId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error('Failed to delete conversation')
  }
}

export interface QueryResponse {
  columns: string[]
  rows: Record<string, unknown>[]
  truncated: boolean
}

export async function fetchDashboardQuery(
  queryName: string,
  params?: DashboardQueryParams
): Promise<QueryResponse> {
  let url = `/api/data/query/${encodeURIComponent(queryName)}`
  if (params) {
    const search = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      search.set(key, String(value))
    }
    const qs = search.toString()
    if (qs) url += `?${qs}`
  }
  const response = await authFetch(url)
  if (!response.ok) {
    throw new Error(`Failed to load query: ${queryName}`)
  }
  return response.json() as Promise<QueryResponse>
}

export async function fetchAdminUsers(): Promise<AdminUser[]> {
  const response = await authFetch('/api/admin/users')
  if (!response.ok) {
    throw new Error('Failed to load users')
  }
  return response.json() as Promise<AdminUser[]>
}

export async function reinviteAdminUser(userId: string): Promise<InviteResponse> {
  const response = await authFetch(`/api/admin/users/${userId}/reinvite`, { method: 'POST' })
  if (!response.ok) {
    const detail = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? 'Failed to generate invite link')
  }
  return response.json() as Promise<InviteResponse>
}

export async function deleteAdminUser(userId: string): Promise<void> {
  const response = await authFetch(`/api/admin/users/${userId}`, { method: 'DELETE' })
  if (!response.ok) {
    const detail = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? 'Failed to delete user')
  }
}

export async function createInvite(email: string): Promise<InviteResponse> {
  const response = await authFetch('/api/admin/invite', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!response.ok) {
    const detail = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail ?? 'Failed to create invite')
  }
  return response.json() as Promise<InviteResponse>
}

export async function createConversation(toolbox?: string): Promise<ConversationCreateResponse> {
  const headers: Record<string, string> = {}
  if (toolbox) headers['x-toolbox'] = toolbox
  const response = await authFetch('/api/conversation', { method: 'POST', headers })
  if (!response.ok) {
    throw new Error('Failed to create conversation')
  }
  return response.json() as Promise<ConversationCreateResponse>
}
