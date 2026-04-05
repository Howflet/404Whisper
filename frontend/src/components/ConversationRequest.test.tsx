import { render, screen, fireEvent } from '@testing-library/react';
import ConversationRequest from '../components/ConversationRequest';
import { vi } from 'vitest';
import type { Conversation } from '../types';

const mockConversation: Conversation = {
  id: 1,
  type: 'DM',
  contact: {
    sessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5c',
    displayName: 'Bob',
  },
  lastMessage: {
    body: 'Hey there!',
    sentAt: '2026-04-04T12:00:00Z',
    senderSessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5c',
  },
  unreadCount: 1,
  groupVibe: null,
  personalVibeOverride: null,
  vibeCooldownUntil: null,
  accepted: false,
  createdAt: '2026-04-04T11:55:00Z',
  updatedAt: '2026-04-04T12:00:00Z',
};

describe('ConversationRequest', () => {
  it('displays pending request for unaccepted conversation', () => {
    render(
      <ConversationRequest
        conversation={mockConversation}
        onAccepted={() => {}}
        onRejected={() => {}}
      />
    );

    expect(screen.getByText(/Bob sent you a message/)).toBeInTheDocument();
    expect(screen.getByText('Accept')).toBeInTheDocument();
    expect(screen.getByText('Reject')).toBeInTheDocument();
  });

  it('does not render for accepted conversation', () => {
    const accepted = { ...mockConversation, accepted: true };
    const { container } = render(
      <ConversationRequest
        conversation={accepted}
        onAccepted={() => {}}
        onRejected={() => {}}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('calls onAccepted when accept button is clicked', async () => {
    const onAccepted = vi.fn();
    render(
      <ConversationRequest
        conversation={mockConversation}
        onAccepted={onAccepted}
        onRejected={() => {}}
      />
    );

    const acceptBtn = screen.getByText('Accept');
    fireEvent.click(acceptBtn);

    expect(screen.getByText('Accepting...')).toBeInTheDocument();
  });

  it('calls onRejected when reject button is clicked', async () => {
    const onRejected = vi.fn();
    render(
      <ConversationRequest
        conversation={mockConversation}
        onAccepted={() => {}}
        onRejected={onRejected}
      />
    );

    const rejectBtn = screen.getByText('Reject');
    fireEvent.click(rejectBtn);

    expect(screen.getByText('Rejecting...')).toBeInTheDocument();
  });
});