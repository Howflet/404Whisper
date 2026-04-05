// API client for REST endpoints

import type { Contact, Conversation, MessageObject, AttachmentObject } from '../types';

const BASE_URL = '/api';

class ApiError extends Error {
  constructor(public code: string, public message: string, public field?: string) {
    super(message);
  }
}

async function apiRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const errorData: { error: { code: string; message: string; field?: string } } = await response.json();
    throw new ApiError(errorData.error.code, errorData.error.message, errorData.error.field);
  }

  return response.json();
}

export const api = {
  // Identity
  createIdentity: (passphrase: string, displayName?: string) =>
    apiRequest<{ sessionId: string; displayName: string | null; mnemonic: string; createdAt: string }>(
      '/identity/new',
      {
        method: 'POST',
        body: JSON.stringify({ passphrase, displayName }),
      }
    ),

  importIdentity: (mnemonic: string, passphrase: string, displayName?: string) =>
    apiRequest<{ sessionId: string; displayName: string | null; createdAt: string }>(
      '/identity/import',
      {
        method: 'POST',
        body: JSON.stringify({ mnemonic, passphrase, displayName }),
      }
    ),

  getIdentity: () =>
    apiRequest<{ sessionId: string; displayName: string | null; personalVibe: string | null; createdAt: string }>(
      '/identity'
    ),

  unlockIdentity: (passphrase: string) =>
    apiRequest<{ ok: true }>('/identity/unlock', {
      method: 'POST',
      body: JSON.stringify({ passphrase }),
    }),

  updateIdentity: (data: { displayName?: string | null; personalVibe?: string | null }) =>
    apiRequest('/identity', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Contacts
  getContacts: (accepted?: boolean) =>
    apiRequest<{ contacts: Contact[] }>(`/contacts${accepted !== undefined ? `?accepted=${accepted}` : ''}`),

  addContact: (sessionId: string, displayName?: string) =>
    apiRequest<{ sessionId: string; displayName: string | null; accepted: boolean; createdAt: string }>(
      '/contacts',
      {
        method: 'POST',
        body: JSON.stringify({ sessionId, displayName }),
      }
    ),

  updateContact: (sessionId: string, data: { displayName?: string | null; accepted?: true }) =>
    apiRequest(`/contacts/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteContact: (sessionId: string) =>
    apiRequest(`/contacts/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    }),

  // Conversations
  getConversations: (type?: 'DM' | 'GROUP') =>
    apiRequest<{ conversations: Conversation[] }>(`/conversations${type ? `?type=${type}` : ''}`),

  getConversationMessages: (id: number, limit?: number, before?: string) =>
    apiRequest<{ messages: MessageObject[]; hasMore: boolean; nextBefore: string | null }>(
      `/conversations/${id}/messages${limit || before ? '?' + new URLSearchParams({
        ...(limit && { limit: limit.toString() }),
        ...(before && { before }),
      }).toString() : ''}`
    ),

  updateConversation: (id: number, data: { personalVibeOverride?: string | null; accepted?: true }) =>
    apiRequest(`/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Messages
  sendMessage: (conversationId: number, body?: string, attachmentId?: number) =>
    apiRequest<MessageObject>('/messages/send', {
      method: 'POST',
      body: JSON.stringify({ conversationId, body, attachmentId }),
    }),

  // Groups
  createGroup: (name: string, memberSessionIds?: string[]) =>
    apiRequest<{
      id: number;
      groupSessionId: string;
      name: string;
      memberCount: number;
      vibe: string | null;
      vibeCooldownUntil: string | null;
      createdAt: string;
    }>('/groups', {
      method: 'POST',
      body: JSON.stringify({ name, memberSessionIds }),
    }),

  getGroup: (id: number) =>
    apiRequest<{
      id: number;
      groupSessionId: string;
      name: string;
      vibe: string | null;
      vibeCooldownUntil: string | null;
      members: Array<{
        sessionId: string;
        displayName: string | null;
        isAdmin: boolean;
        joinedAt: string;
      }>;
      createdAt: string;
      updatedAt: string;
    }>(`/groups/${id}`),

  updateGroup: (id: number, data: { name?: string; vibe?: string | null }) =>
    apiRequest(`/groups/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  addGroupMembers: (id: number, sessionIds: string[]) =>
    apiRequest('/groups/${id}/members', {
      method: 'POST',
      body: JSON.stringify({ sessionIds }),
    }),

  removeGroupMember: (id: number, sessionId: string) =>
    apiRequest(`/groups/${id}/members/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    }),

  leaveGroup: (id: number) =>
    apiRequest<{ ok: true }>(`/groups/${id}/leave`, {
      method: 'POST',
    }),

  // Attachments
  uploadAttachment: (file: File, conversationId: number) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('conversationId', conversationId.toString());

    return apiRequest<AttachmentObject>('/attachments/upload', {
      method: 'POST',
      body: formData,
      headers: {}, // Let browser set content-type for multipart
    });
  },

  downloadAttachment: (id: number) =>
    fetch(`${BASE_URL}/attachments/${id}`),
};

export { ApiError };