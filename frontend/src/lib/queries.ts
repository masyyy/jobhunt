import type { UIMessage } from '@ai-sdk/react'

import { apiFetch } from './auth'

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

export type JobCategory =
  | 'retail'
  | 'craft'
  | 'bookstore'
  | 'library'
  | 'museum'
  | 'culture'
  | 'other'
export type JobStatus = 'new' | 'interested' | 'applied' | 'dismissed'
export type JobSourceName = 'duunitori' | 'tyomarkkinatori' | 'kuntarekry'

export interface Job {
  id: string
  source: JobSourceName
  title: string
  employer: string | null
  location: string | null
  url: string
  posted_at: string | null
  category: JobCategory
  relevance_score: number
  match_reason: string | null
  application_cover_letter: string | null
  application_how_to_apply: string | null
  status: JobStatus
}

export interface JobApplication {
  cover_letter: string
  how_to_apply: string
}

export interface JobFilters {
  category?: JobCategory
  source?: JobSourceName
  status?: JobStatus
  search?: string
  relevant_only?: boolean
}

export const queryKeys = {
  conversations: (toolbox?: string) => ['conversations', toolbox] as const,
  conversationHistory: (id: string | null, toolbox?: string) =>
    ['conversationHistory', id, toolbox] as const,
  taskOutputs: (taskName: string, toolbox?: string) => ['taskOutputs', taskName, toolbox] as const,
  dashboardQuery: (queryName: string, params?: DashboardQueryParams) =>
    ['dashboardQuery', queryName, params ?? null] as const,
  jobs: (filters?: JobFilters) => ['jobs', filters ?? null] as const,
}

export async function fetchConversations(toolbox?: string): Promise<ConversationItem[]> {
  const params = new URLSearchParams()
  if (toolbox) params.set('toolbox', toolbox)
  const qs = params.toString()
  const url = qs ? `/api/conversations?${qs}` : '/api/conversations'
  const response = await apiFetch(url)
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
  const response = await apiFetch(url)
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
  const response = await apiFetch(`/api/task-outputs?${params.toString()}`)
  if (!response.ok) {
    throw new Error('Failed to load task outputs')
  }
  return response.json() as Promise<TaskOutput[]>
}

export async function updateTaskOutputState(
  outputId: string,
  state: SignalState
): Promise<TaskOutput> {
  const response = await apiFetch(`/api/task-outputs/${outputId}`, {
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
  const response = await apiFetch(`/api/conversation/${conversationId}`, {
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
  const response = await apiFetch(url)
  if (!response.ok) {
    throw new Error(`Failed to load query: ${queryName}`)
  }
  return response.json() as Promise<QueryResponse>
}

export async function fetchJobs(filters?: JobFilters): Promise<Job[]> {
  const params = new URLSearchParams()
  if (filters?.category) params.set('category', filters.category)
  if (filters?.source) params.set('source', filters.source)
  if (filters?.status) params.set('status', filters.status)
  if (filters?.search) params.set('search', filters.search)
  if (filters?.relevant_only === false) params.set('relevant_only', 'false')
  const qs = params.toString()
  const response = await apiFetch(`/api/jobs${qs ? `?${qs}` : ''}`)
  if (!response.ok) {
    throw new Error('Failed to load jobs')
  }
  return response.json() as Promise<Job[]>
}

export async function updateJobStatus(jobId: string, status: JobStatus): Promise<Job> {
  const response = await apiFetch(`/api/jobs/${jobId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
  if (!response.ok) {
    throw new Error('Failed to update job status')
  }
  return response.json() as Promise<Job>
}

export async function draftJobApplication(
  jobId: string,
  regenerate = false
): Promise<JobApplication> {
  const qs = regenerate ? '?regenerate=true' : ''
  const response = await apiFetch(`/api/jobs/${jobId}/application${qs}`, { method: 'POST' })
  if (!response.ok) {
    throw new Error('Failed to draft application')
  }
  return response.json() as Promise<JobApplication>
}

export async function createConversation(toolbox?: string): Promise<ConversationCreateResponse> {
  const headers: Record<string, string> = {}
  if (toolbox) headers['x-toolbox'] = toolbox
  const response = await apiFetch('/api/conversation', { method: 'POST', headers })
  if (!response.ok) {
    throw new Error('Failed to create conversation')
  }
  return response.json() as Promise<ConversationCreateResponse>
}
