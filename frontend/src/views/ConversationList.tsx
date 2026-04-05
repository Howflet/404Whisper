import React, { useState } from 'react';
import { useApp } from '../App';
import { api, ApiError } from '../api/client';
import ConversationRequest from '../components/ConversationRequest';
import type { Conversation } from '../types';

function ConversationList() {
  const { conversations, currentConversation, setCurrentConversation, refreshConversations, openSettings, openGroupCreate } = useApp();
  const [showAddContact, setShowAddContact] = useState(false);
  const [contactId, setContactId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const formatLastMessage = (conv: Conversation) => {
    if (!conv.lastMessage) return 'No messages yet';
    const body = conv.lastMessage.body || '[Attachment]';
    const sender = conv.lastMessage.senderSessionId === conv.contact?.sessionId ? '' : 'You: ';
    return `${sender}${body.slice(0, 50)}${body.length > 50 ? '...' : ''}`;
  };

  const handleAddContact = async (e: React.FormEvent) => {
    e.preventDefault();
    setAdding(true);
    setError(null);

    try {
      await api.addContact(contactId, displayName || undefined);
      await refreshConversations();
      setShowAddContact(false);
      setContactId('');
      setDisplayName('');
    } catch (error) {
      if (error instanceof ApiError) {
        setError(error.message);
      } else {
        setError('Failed to add contact');
      }
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="conversation-list">
      <div className="conversation-list-header">
        <h2>Conversations</h2>
        <button className="settings-btn" onClick={openSettings} title="Settings">
          ⚙️
        </button>
      </div>
      <div className="conversation-list-actions">
        <button onClick={() => setShowAddContact(!showAddContact)} className="add-contact-btn">
          {showAddContact ? 'Cancel' : 'Add Contact'}
        </button>
        <button onClick={openGroupCreate} className="create-group-btn">
          Create Group
        </button>
      </div>

      {showAddContact && (
        <form onSubmit={handleAddContact} className="add-contact-form">
          <div>
            <label htmlFor="contactId">Session ID:</label>
            <input
              type="text"
              id="contactId"
              value={contactId}
              onChange={(e) => setContactId(e.target.value)}
              placeholder="057aeb66e45660c3..."
              pattern="^05[0-9a-f]{64}$"
              required
            />
          </div>
          <div>
            <label htmlFor="displayName">Display Name (optional):</label>
            <input
              type="text"
              id="displayName"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Friend's name"
              maxLength={64}
            />
          </div>
          {error && <div className="error">{error}</div>}
          <button type="submit" disabled={adding}>
            {adding ? 'Adding...' : 'Add Contact'}
          </button>
        </form>
      )}

      {/* Pending conversation requests */}
      {conversations
        .filter((conv) => !conv.accepted)
        .map((conv) => (
          <ConversationRequest
            key={conv.id}
            conversation={conv}
            onAccepted={() => refreshConversations()}
            onRejected={() => refreshConversations()}
          />
        ))}

      {conversations.length === 0 ? (
        <p>No conversations yet. Add a contact to start chatting.</p>
      ) : (
        <ul>
          {conversations.map((conv) => (
            <li
              key={conv.id}
              className={currentConversation?.id === conv.id ? 'active' : ''}
              onClick={() => setCurrentConversation(conv)}
            >
              <div className="conversation-name">
                {conv.type === 'DM' ? conv.contact?.displayName || conv.contact?.sessionId : conv.group?.name}
              </div>
              <div className="last-message">{formatLastMessage(conv)}</div>
              {conv.unreadCount > 0 && <span className="unread">{conv.unreadCount}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default ConversationList;