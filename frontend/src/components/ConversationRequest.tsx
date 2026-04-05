import React, { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Conversation } from '../types';

interface ConversationRequestProps {
  conversation: Conversation;
  onAccepted: () => void;
  onRejected: () => void;
}

function ConversationRequest({ conversation, onAccepted, onRejected }: ConversationRequestProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const contactName =
    conversation.type === 'DM'
      ? conversation.contact?.displayName || conversation.contact?.sessionId
      : conversation.group?.name;

  const handleAccept = async () => {
    setLoading(true);
    setError(null);

    try {
      await api.updateConversation(conversation.id, { accepted: true });
      onAccepted();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to accept conversation');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    setError(null);

    try {
      // Note: There's no explicit rejection API in the contract, so we just don't accept
      // In a real app, you might want to delete/block the conversation
      onRejected();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to handle conversation');
      }
    } finally {
      setLoading(false);
    }
  };

  if (conversation.accepted) {
    return null;
  }

  return (
    <div className="conversation-request">
      <div className="request-content">
        <p>
          <strong>{contactName}</strong> sent you a message
        </p>
        {error && <div className="error">{error}</div>}
      </div>
      <div className="request-actions">
        <button
          onClick={handleAccept}
          disabled={loading}
          className="accept-btn"
        >
          {loading ? 'Accepting...' : 'Accept'}
        </button>
        <button
          onClick={handleReject}
          disabled={loading}
          className="reject-btn"
        >
          {loading ? 'Rejecting...' : 'Reject'}
        </button>
      </div>
    </div>
  );
}

export default ConversationRequest;