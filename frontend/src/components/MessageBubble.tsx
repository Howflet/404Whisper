import React from 'react';
import type { MessageObject, Identity } from '../types';

interface MessageBubbleProps {
  message: MessageObject;
  identity: Identity;
}

function MessageBubble({ message, identity }: MessageBubbleProps) {
  const formatTime = (dateString: string) => {
    return new Date(dateString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const isOwnMessage = message.senderSessionId === identity.sessionId;

  return (
    <div className={`message-bubble ${isOwnMessage ? 'own' : 'other'}`}>
      <div className="message-content">
        {message.body && <p>{message.body}</p>}
        {message.attachment && (
          <div className="attachment">
            <span>{message.attachment.fileName}</span>
            <span>({Math.round(message.attachment.fileSize / 1024)} KB)</span>
          </div>
        )}
      </div>
      <div className="message-meta">
        <span className="time">{formatTime(message.sentAt)}</span>
        {!isOwnMessage && message.senderSessionId && <span className="sender">{message.senderSessionId.slice(0, 10)}...</span>}
      </div>
    </div>
  );
}

export default MessageBubble;