import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { vi } from 'vitest';
import type { Identity, Conversation, MessageObject } from '../types';

// Mock API client
vi.mock('../api/client', () => {
  const mockApi = {
    getIdentity: vi.fn(),
    createIdentity: vi.fn(),
    unlockIdentity: vi.fn(),
    updateIdentity: vi.fn(),
    getConversations: vi.fn(),
    getConversationMessages: vi.fn(),
    sendMessage: vi.fn(),
    addContact: vi.fn(),
    updateContact: vi.fn(),
    createGroup: vi.fn(),
    getGroup: vi.fn(),
    uploadAttachment: vi.fn(),
  };

  return {
    api: mockApi,
    ApiError: class ApiError extends Error {
      constructor(public code: string, public message: string, public field?: string) {
        super(message);
      }
    },
  };
});

// Mock WebSocket client
vi.mock('../api/socket', () => ({
  wsClient: {
    connect: vi.fn(),
    disconnect: vi.fn(),
    onMessage: vi.fn(() => vi.fn()),
  },
}));

describe('Frontend Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Identity Setup and Unlock Flow', () => {
    it('shows setup screen when no identity exists', async () => {
      const { api } = await import('../api/client');
      (api.getIdentity as any).mockRejectedValueOnce(new Error('No identity'));

      render(<App />);

      expect(screen.getByText('404Whisper Setup')).toBeInTheDocument();
    });

    it('progresses through identity creation', async () => {
      const { api } = await import('../api/client');
      const createdIdentity: Identity = {
        sessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b',
        displayName: 'Alice',
        personalVibe: null,
        createdAt: '2026-04-04T12:00:00Z',
      };

      (api.getIdentity as any)
        .mockRejectedValueOnce(new Error('No identity'))
        .mockResolvedValueOnce(createdIdentity);

      (api.createIdentity as any).mockResolvedValueOnce({
        ...createdIdentity,
        mnemonic: 'word1 word2 word3 ...',
      });

      render(<App />);

      // Fill in form
      const passphraseInput = screen.getByPlaceholderText('Choose a strong passphrase');
      await userEvent.type(passphraseInput, 'hunter2hunter2');

      const displayNameInput = screen.getByPlaceholderText('Your display name');
      await userEvent.type(displayNameInput, 'Alice');

      // Submit
      const createBtn = screen.getByText('Create Identity');
      fireEvent.click(createBtn);

      // Should show mnemonic
      await waitFor(() => {
        expect(screen.getByText('Identity Created!')).toBeInTheDocument();
      });
    });
  });

  describe('Conversation Management', () => {
    beforeEach(async () => {
      const { api } = await import('../api/client');
      const identity: Identity = {
        sessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b',
        displayName: 'Alice',
        personalVibe: null,
        createdAt: '2026-04-04T12:00:00Z',
      };

      (api.getIdentity as any).mockResolvedValue(identity);
      (api.getConversations as any).mockResolvedValue({ conversations: [] });
    });

    it('displays conversation list', async () => {
      render(<App />);

      await waitFor(() => {
        expect(screen.getByText('Conversations')).toBeInTheDocument();
      });
    });

    it('shows settings button in conversation list', async () => {
      render(<App />);

      await waitFor(() => {
        const settingsBtn = screen.getByTitle('Settings');
        expect(settingsBtn).toBeInTheDocument();
      });
    });

    it('opens settings panel from settings button', async () => {
      const { api } = await import('../api/client');
      const identity: Identity = {
        sessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b',
        displayName: 'Alice',
        personalVibe: null,
        createdAt: '2026-04-04T12:00:00Z',
      };

      (api.getIdentity as any).mockResolvedValue(identity);
      (api.getConversations as any).mockResolvedValue({ conversations: [] });

      render(<App />);

      await waitFor(() => {
        const settingsBtn = screen.getByTitle('Settings');
        fireEvent.click(settingsBtn);
      });

      await waitFor(() => {
        expect(screen.getByText('Your Session ID')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Alice')).toBeInTheDocument();
      });
    });

    it('allows adding a new contact', async () => {
      const { api } = await import('../api/client');
      const identity: Identity = {
        sessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b',
        displayName: 'Alice',
        personalVibe: null,
        createdAt: '2026-04-04T12:00:00Z',
      };

      (api.getIdentity as any).mockResolvedValue(identity);
      (api.getConversations as any).mockResolvedValue({ conversations: [] });
      (api.addContact as any).mockResolvedValue({
        sessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5c',
        displayName: 'Bob',
        accepted: true,
        createdAt: '2026-04-04T12:05:00Z',
      });

      render(<App />);

      await waitFor(() => {
        const addContactBtn = screen.getByText('Add Contact');
        fireEvent.click(addContactBtn);
      });

      const sessionIdInput = screen.getByPlaceholderText('057aeb66e45660c3...');
      await userEvent.type(
        sessionIdInput,
        '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5c'
      );

      const addBtn = screen.getByText('Add Contact');
      fireEvent.click(addBtn);

      expect(api.addContact).toHaveBeenCalled();
    });

    it('shows group creation button', async () => {
      const { api } = await import('../api/client');
      (api.getIdentity as any).mockResolvedValue({
        sessionId: '05abc',
        displayName: 'Alice',
        personalVibe: null,
        createdAt: '2026-04-04T12:00:00Z',
      });
      (api.getConversations as any).mockResolvedValue({ conversations: [] });

      render(<App />);

      await waitFor(() => {
        const createGroupBtn = screen.getByText('Create Group');
        expect(createGroupBtn).toBeInTheDocument();
      });
    });
  });
});