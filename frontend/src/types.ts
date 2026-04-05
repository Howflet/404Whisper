// Types based on DATA_CONTRACT.md

export type VibeId =
  | "CAMPFIRE"
  | "NEON"
  | "LIBRARY"
  | "VOID"
  | "SUNRISE"
  | "404"
  | "CONFESSIONAL"
  | "SLOW_BURN"
  | "CHORUS"
  | "SPOTLIGHT"
  | "ECHO"
  | "SCRAMBLE";

export type AttachmentStatus = "PENDING" | "UPLOADING" | "UPLOADED" | "DOWNLOADING" | "DOWNLOADED" | "FAILED";

export type MessageType = "TEXT" | "ATTACHMENT" | "GROUP_EVENT" | "SYSTEM";

export type GroupEventType = "MEMBER_JOINED" | "MEMBER_LEFT" | "VIBE_CHANGED" | "GROUP_RENAMED";

export type ConversationType = "DM" | "GROUP";

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    field?: string;
    details?: unknown;
  };
}

export interface Identity {
  sessionId: string;
  displayName: string | null;
  personalVibe: VibeId | null;
  createdAt: string;
}

export interface Contact {
  sessionId: string;
  displayName: string | null;
  accepted: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface Group {
  id: number;
  groupSessionId: string;
  name: string;
  memberCount: number;
  vibe: VibeId | null;
  vibeCooldownUntil: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Conversation {
  id: number;
  type: ConversationType;
  contact?: {
    sessionId: string;
    displayName: string | null;
  };
  group?: Group;
  lastMessage: {
    body: string | null;
    sentAt: string;
    senderSessionId: string;
  } | null;
  unreadCount: number;
  groupVibe: VibeId | null;
  personalVibeOverride: VibeId | null;
  vibeCooldownUntil: string | null;
  accepted: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AttachmentObject {
  id: number;
  fileName: string;
  fileSize: number;
  mimeType: string;
  status: AttachmentStatus;
  createdAt: string;
}

export interface MessageObject {
  id: number;
  conversationId: number;
  senderSessionId: string | null;
  body: string | null;
  type: MessageType;
  sentAt: string;
  receivedAt: string | null;
  expiresAt: string | null;
  deliverAfter: string | null;
  isAnonymous: boolean;
  isSpotlightPinned: boolean;
  attachment: AttachmentObject | null;
  groupEventType: GroupEventType | null;
  vibeMetadata: {
    activeVibe: VibeId | null;
  } | null;
}

export interface WSEvent {
  event: string;
  payload: unknown;
}

export interface MessageReceivedEvent extends WSEvent {
  event: "message_received";
  payload: MessageObject;
}

export interface AttachmentProgressEvent extends WSEvent {
  event: "attachment_progress";
  payload: {
    attachmentId: number;
    status: AttachmentStatus;
    progressPercent: number;
  };
}

export interface VibeChangedEvent extends WSEvent {
  event: "vibe_changed";
  payload: {
    conversationId: number;
    newVibe: VibeId | null;
    changedBySessionId: string;
    cooldownUntil: string;
    isBehavioral: boolean;
  };
}

export interface ConversationRequestEvent extends WSEvent {
  event: "conversation_request";
  payload: {
    conversationId: number;
    fromSessionId: string;
  };
}

export interface IdentityLockedEvent extends WSEvent {
  event: "identity_locked";
  payload: {};
}