import { api } from './client'
import type {
  Conversation,
  ConversationDetail,
  ModelsResponse,
  Page,
  UsageResponse,
  User,
} from './types'

export const auth = {
  me: () => api<User>('/api/auth/me/'),
  login: (email: string, password: string) => api<User>('/api/auth/login/', { method: 'POST', json: { email, password } }),
  register: (email: string, password: string, display_name: string) =>
    api<User>('/api/auth/register/', { method: 'POST', json: { email, password, display_name } }),
  logout: () => api<void>('/api/auth/logout/', { method: 'POST' }),
  updateMe: (patch: Partial<Pick<User, 'display_name'>>) => api<User>('/api/auth/me/', { method: 'PATCH', json: patch }),
}

export const conversations = {
  list: (params: { q?: string; archived?: boolean } = {}) => {
    const search = new URLSearchParams({ limit: '100' })
    if (params.q) search.set('q', params.q)
    if (params.archived !== undefined) search.set('archived', String(params.archived))
    return api<Page<Conversation>>(`/api/conversations/?${search}`)
  },
  get: (id: number) => api<ConversationDetail>(`/api/conversations/${id}/`),
  create: (model_id?: string) => api<Conversation>('/api/conversations/', { method: 'POST', json: model_id ? { model_id } : {} }),
  update: (id: number, patch: Partial<Pick<Conversation, 'title' | 'archived' | 'model_id'>>) =>
    api<Conversation>(`/api/conversations/${id}/`, { method: 'PATCH', json: patch }),
  remove: (id: number) => api<void>(`/api/conversations/${id}/`, { method: 'DELETE' }),
  exportUrl: (id: number, fmt: 'md' | 'txt') => `/api/conversations/${id}/export/?fmt=${fmt}`,
}

export const models = { list: () => api<ModelsResponse>('/api/models/') }
export const usage = { me: () => api<UsageResponse>('/api/usage/me/') }
