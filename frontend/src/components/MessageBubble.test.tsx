import { render, screen } from '@testing-library/react';
import MessageBubble from '../components/MessageBubble';
import type { MessageObject, Identity } from '../types';

const mockIdentity: Identity = {
  sessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b',
  displayName: 'Alice',
  personalVibe: null,
  createdAt: '2026-04-04T12:00:00Z',
};

const mockMessage: MessageObject = {
  id: 1,
  conversationId: 1,
  senderSessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5c', // Different from identity
  body: 'Hello world',
  type: 'TEXT',
  sentAt: '2026-04-04T12:05:00Z',
  receivedAt: null,
  expiresAt: null,
  deliverAfter: null,
  isAnonymous: false,
  isSpotlightPinned: false,
  attachment: null,
  groupEventType: null,
  vibeMetadata: null,
};

describe('MessageBubble', () => {
  it('renders message content', () => {
    render(<MessageBubble message={mockMessage} identity={mockIdentity} />);
    
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  it('shows sender for other messages', () => {
    render(<MessageBubble message={mockMessage} identity={mockIdentity} />);
    
    expect(screen.getByText('057aeb66e4...')).toBeInTheDocument();
  });

  it('does not show sender for own messages', () => {
    const ownMessage = { ...mockMessage, senderSessionId: mockIdentity.sessionId };
    render(<MessageBubble message={ownMessage} identity={mockIdentity} />);
    
    expect(screen.queryByText('057aeb66e4...')).not.toBeInTheDocument();
  });

  it('displays time correctly', () => {
    render(<MessageBubble message={mockMessage} identity={mockIdentity} />);
    
    expect(screen.getByText('12:05')).toBeInTheDocument();
  });
});