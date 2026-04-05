import React, { useState } from 'react';
import { useApp } from '../App';
import { api, ApiError } from '../api/client';
import MessageBubble from '../components/MessageBubble';
import GroupMembers from '../components/GroupMembers';
import AttachmentUpload from '../components/AttachmentUpload';
import AttachmentProgress from '../components/AttachmentProgress';
import type { AttachmentStatus } from '../types';

function ChatView() {
  const { currentConversation, messages, sendMessage, identity } = useApp();
  const [messageText, setMessageText] = useState('');
  const [sending, setSending] = useState(false);
  const [showMembers, setShowMembers] = useState(false);
  const [attachments, setAttachments] = useState<
    Map<
      string,
      {
        fileName: string;
        status: AttachmentStatus;
        progressPercent: number;
        error?: string;
      }
    >
  >(new Map());

  if (!currentConversation) return null;

  const handleFileUpload = async (file: File) => {
    if (!currentConversation) return;

    const uploadKey = `${Date.now()}-${file.name}`;
    setAttachments(new Map(attachments).set(uploadKey, {
      fileName: file.name,
      status: 'PENDING',
      progressPercent: 0,
    }));

    try {
      // Update status to UPLOADING
      setAttachments((old) => {
        const updated = new Map(old);
        updated.set(uploadKey, {
          ...updated.get(uploadKey)!,
          status: 'UPLOADING',
          progressPercent: 0,
        });
        return updated;
      });

      // Simulate progress (in real app, use XMLHttpRequest or fetch with progress events)
      let progress = 10;
      const interval = setInterval(() => {
        if (progress < 90) {
          progress += Math.random() * 40;
          setAttachments((old) => {
            const updated = new Map(old);
            updated.set(uploadKey, {
              ...updated.get(uploadKey)!,
              progressPercent: Math.min(progress, 90),
            });
            return updated;
          });
        }
      }, 200);

      const attachment = await api.uploadAttachment(file, currentConversation.id);
      clearInterval(interval);

      // Update to UPLOADED
      setAttachments((old) => {
        const updated = new Map(old);
        updated.set(uploadKey, {
          ...updated.get(uploadKey)!,
          status: 'UPLOADED',
          progressPercent: 100,
        });
        return updated;
      });

      // Auto-send message with attachment
      try {
        await sendMessage('');
      } catch (error) {
        console.error('Failed to send message with attachment:', error);
      }

      // Remove from UI after 2 seconds
      setTimeout(() => {
        setAttachments((old) => {
          const updated = new Map(old);
          updated.delete(uploadKey);
          return updated;
        });
      }, 2000);
    } catch (err) {
      const errorMessage = err instanceof ApiError ? err.message : 'Upload failed';
      setAttachments((old) => {
        const updated = new Map(old);
        updated.set(uploadKey, {
          ...updated.get(uploadKey)!,
          status: 'FAILED',
          error: errorMessage,
        });
        return updated;
      });
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!messageText.trim() || sending) return;

    setSending(true);
    try {
      await sendMessage(messageText.trim());
      setMessageText('');
    } catch (error) {
      console.error('Failed to send message:', error);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="chat-view">
      <div className="chat-header">
        <h2>
          {currentConversation.type === 'DM'
            ? currentConversation.contact?.displayName || currentConversation.contact?.sessionId
            : currentConversation.group?.name
          }
        </h2>
        {currentConversation.type === 'GROUP' && (
          <button
            className="members-btn"
            onClick={() => setShowMembers(true)}
            title="View members"
          >
            👥
          </button>
        )}
      </div>

      <div className="messages">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} identity={identity!} />
        ))}
      </div>

      <form className="message-input" onSubmit={handleSend}>
        <input
          type="text"
          value={messageText}
          onChange={(e) => setMessageText(e.target.value)}
          placeholder="Type a message..."
          disabled={sending}
        />
        <AttachmentUpload onFileSelected={handleFileUpload} disabled={sending} />
        <button type="submit" disabled={!messageText.trim() || sending}>
          {sending ? 'Sending...' : 'Send'}
        </button>
      </form>

      {/* Attachment progress list */}
      {attachments.size > 0 && (
        <div className="attachment-list">
          {Array.from(attachments.values()).map((attachment, idx) => (
            <AttachmentProgress
              key={idx}
              fileName={attachment.fileName}
              status={attachment.status}
              progressPercent={attachment.progressPercent}
              error={attachment.error}
            />
          ))}
        </div>
      )}

      {showMembers && currentConversation.type === 'GROUP' && currentConversation.group && (
        <GroupMembers
          groupId={currentConversation.group.id}
          isAdmin={false} // TODO: Check if current user is admin
          onClose={() => setShowMembers(false)}
        />
      )}
    </div>
  );
}

export default ChatView;