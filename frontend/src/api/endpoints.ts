import { api } from './client'
import type {
  Conversation,
  ConversationDetail,
  DocumentInfo,
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
  create: (body: { model_id?: string; document_ids?: number[] } = {}) =>
    api<Conversation>('/api/conversations/', { method: 'POST', json: body }),
  update: (id: number, patch: Partial<Pick<Conversation, 'title' | 'archived' | 'model_id' | 'document_ids'>>) =>
    api<Conversation>(`/api/conversations/${id}/`, { method: 'PATCH', json: patch }),
  remove: (id: number) => api<void>(`/api/conversations/${id}/`, { method: 'DELETE' }),
  exportUrl: (id: number, fmt: 'md' | 'txt') => `/api/conversations/${id}/export/?fmt=${fmt}`,
}

export const models = { list: () => api<ModelsResponse>('/api/models/') }
export const usage = { me: () => api<UsageResponse>('/api/usage/me/') }

export const documents = {
  list: () => api<Page<DocumentInfo>>('/api/documents/?limit=200'),
  get: (id: number) => api<DocumentInfo>(`/api/documents/${id}/`),
  upload: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return api<DocumentInfo>('/api/documents/', { method: 'POST', body })
  },
  remove: (id: number) => api<void>(`/api/documents/${id}/`, { method: 'DELETE' }),
  reprocess: (id: number) => api<DocumentInfo>(`/api/documents/${id}/reprocess/`, { method: 'POST' }),
  downloadUrl: (id: number) => `/api/documents/${id}/download/`,
}

export const ACCEPTED_FILES =
  '.pdf,.docx,.xlsx,.csv,.txt,.md,.markdown,.json,.py,.js,.ts,.tsx,.jsx,.java,.go,.rb,.php,.cs,.c,.h,.cpp,.rs,.kt,.swift,.sql,.html,.css,.yaml,.yml,.toml,.xml,.sh,.dart'
