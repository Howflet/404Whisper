import React, { useState, useEffect, createContext, useContext } from 'react';
import { api, ApiError } from './api/client';
import { wsClient } from './api/socket';
import type { Identity, Conversation, MessageObject, WSEvent } from './types';
import Setup from './views/Setup';
import Unlock from './views/Unlock';
import ConversationList from './views/ConversationList';
import ChatView from './views/ChatView';
import SettingsPanel from './components/SettingsPanel';
import GroupCreate from './views/GroupCreate';

interface AppContextType {
  identity: Identity | null;
  isUnlocked: boolean;
  conversations: Conversation[];
  currentConversation: Conversation | null;
  messages: MessageObject[];
  setCurrentConversation: (conv: Conversation | null) => void;
  refreshConversations: () => Promise<void>;
  refreshMessages: () => Promise<void>;
  sendMessage: (body: string) => Promise<void>;
  openSettings: () => void;
  openGroupCreate: () => void;
}

const AppContext = createContext<AppContextType | null>(null);

export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) throw new Error('useApp must be used within AppProvider');
  return context;
};

function App() {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [isUnlocked, setIsUnlocked] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<MessageObject[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [showGroupCreate, setShowGroupCreate] = useState(false);

  useEffect(() => {
    checkIdentity();
  }, []);

  useEffect(() => {
    if (isUnlocked) {
      wsClient.connect();
      loadConversations();
      return () => wsClient.disconnect();
    }
  }, [isUnlocked]);

  useEffect(() => {
    if (isUnlocked) {
      const unsubscribe = wsClient.onMessage(handleWSEvent);
      return unsubscribe;
    }
  }, [isUnlocked]);

  useEffect(() => {
    if (currentConversation) {
      loadMessages();
      // Mark messages as read by resetting unread count
      setConversations(prev => prev.map(conv =>
        conv.id === currentConversation.id ? { ...conv, unreadCount: 0 } : conv
      ));
    } else {
      setMessages([]);
    }
  }, [currentConversation]);

  const checkIdentity = async () => {
    try {
      const id = await api.getIdentity();
      setIdentity(id);
      setIsUnlocked(true);
    } catch (error) {
      if (error instanceof ApiError && error.code === 'IDENTITY_LOCKED') {
        try {
          const id = await api.getIdentity();
          setIdentity(id);
        } catch {
          // No identity yet
        }
      }
    }
  };

  const loadConversations = async () => {
    try {
      const { conversations: convs } = await api.getConversations();
      setConversations(convs);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadMessages = async () => {
    if (!currentConversation) return;
    try {
      const { messages: msgs } = await api.getConversationMessages(currentConversation.id);
      setMessages(msgs);
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  };

  const handleWSEvent = (event: WSEvent) => {
    switch (event.event) {
      case 'message_received':
        const message = event.payload as MessageObject;
        // Update messages if it's the current conversation
        if (message.conversationId === currentConversation?.id) {
          setMessages(prev => [...prev, message]);
          // Mark as read immediately when message arrives while viewing conversation
          setConversations(prev => prev.map(conv =>
            conv.id === message.conversationId
              ? { ...conv, lastMessage: { body: message.body, sentAt: message.sentAt, senderSessionId: message.senderSessionId || '' }, unreadCount: 0 }
              : conv
          ));
        } else {
          // Increment unread count for other conversations
          setConversations(prev => prev.map(conv =>
            conv.id === message.conversationId
              ? { 
                  ...conv, 
                  lastMessage: { body: message.body, sentAt: message.sentAt, senderSessionId: message.senderSessionId || '' },
                  unreadCount: conv.unreadCount + 1
                }
              : conv
          ));
        }
        break;
      case 'identity_locked':
        setIsUnlocked(false);
        break;
      // Handle other events...
    }
  };

  const refreshConversations = async () => {
    await loadConversations();
  };

  const refreshMessages = async () => {
    await loadMessages();
  };

  const sendMessage = async (body: string) => {
    if (!currentConversation) return;
    try {
      const message = await api.sendMessage(currentConversation.id, body);
      setMessages(prev => [...prev, message]);
      // Update conversation
      setConversations(prev => prev.map(conv =>
        conv.id === currentConversation.id
          ? { ...conv, lastMessage: { body: message.body, sentAt: message.sentAt, senderSessionId: message.senderSessionId || '' } }
          : conv
      ));
    } catch (error) {
      console.error('Failed to send message:', error);
    }
  };

  const contextValue: AppContextType = {
    identity,
    isUnlocked,
    conversations,
    currentConversation,
    messages,
    setCurrentConversation,
    refreshConversations,
    refreshMessages,
    sendMessage,
    openSettings: () => setShowSettings(true),
    openGroupCreate: () => setShowGroupCreate(true),
  };

  if (!identity) {
    return <Setup onIdentityCreated={setIdentity} />;
  }

  if (!isUnlocked) {
    return <Unlock onUnlocked={() => setIsUnlocked(true)} />;
  }

  return (
    <AppContext.Provider value={contextValue}>
      <div className="app">
        <ConversationList />
        {currentConversation && <ChatView />}
        {showSettings && identity && (
          <SettingsPanel
            sessionId={identity.sessionId}
            displayName={identity.displayName}
            personalVibe={identity.personalVibe}
            onClose={() => setShowSettings(false)}
            onUpdate={() => {
              checkIdentity();
            }}
          />
        )}
        {showGroupCreate && (
          <GroupCreate
            onClose={() => setShowGroupCreate(false)}
            onCreated={() => {
              refreshConversations();
            }}
          />
        )}
      </div>
    </AppContext.Provider>
  );
}

export default App;