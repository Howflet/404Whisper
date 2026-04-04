# 404Whisper — Data Contract

> **Version:** 0.2.0 — All open questions resolved; contract is now implementation-ready.
> **Status:** Approved
> **Audience:** Frontend developer (React/TypeScript) and database developer (SQLite/sqlcipher3).
> **Change from 0.1.0:** All 12 open questions closed. Added `isPinned`/`chorusGroupId` to `MessageObject`, pin endpoints, `is_pinned`/`chorus_group_id` DB columns, and confirmed all numeric thresholds.

---

## Naming Conventions

| Layer | Convention | Example |
|---|---|---|
| API request/response fields | `camelCase` | `sessionId`, `displayName` |
| Python model fields (Pydantic) | `snake_case` | `session_id`, `display_name` |
| Database column names | `snake_case` | `session_id`, `display_name` |
| Database table names | `snake_case`, plural | `contacts`, `group_members` |
| Enum values (API + DB) | `SCREAMING_SNAKE_CASE` | `CAMPFIRE`, `SLOW_BURN` |
| WebSocket event types | `snake_case` | `message_received`, `vibe_changed` |

---

## Transport & Base URL

- **Base URL:** `http://localhost:8000/api` — FastAPI default port **8000**; overridable via `WHISPER_PORT` environment variable.
- **WebSocket:** `ws://localhost:8000/ws` — same port as REST API.
- **Vite dev server:** port **5173** (frontend only; proxies `/api` and `/ws` to 8000 during development).
- **Auth:** No token-based auth. All endpoints are localhost-only. A **session unlock** step (passphrase challenge) gates access to the identity on first use and after **15 minutes of inactivity** (see Identity section and OQ-10 resolution).
- **Content-Type:** `application/json` for all REST endpoints unless otherwise noted.
- **File uploads:** `multipart/form-data`.
- **Maximum attachment size:** 10,485,760 bytes (10 MiB). Requests exceeding this are rejected with `ATTACHMENT_TOO_LARGE` (413) before the file is processed.

---

## Shared Error Contract

All error responses use the following envelope:

```typescript
type ErrorResponse = {
  error: {
    code: string;        // Machine-readable error code (see codes below)
    message: string;     // Human-readable description
    field?: string;      // Populated when the error is field-specific (validation errors)
    details?: unknown;   // Optional extra context; shape varies by code
  };
};
```

### Standard Error Codes

| HTTP Status | `error.code` | Meaning |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Request body/param failed validation; `field` will identify the offending field |
| 400 | `INVALID_SESSION_ID` | A Session ID failed format validation (not 66 hex chars with `05` prefix) |
| 400 | `MALFORMED_REQUEST` | Unparseable request body |
| 404 | `NOT_FOUND` | Referenced resource does not exist |
| 409 | `ALREADY_EXISTS` | Duplicate resource (e.g. contact already added) |
| 409 | `IDENTITY_ALREADY_CREATED` | Attempt to call `new` or `import` when an identity already exists |
| 409 | `VIBE_COOLDOWN_ACTIVE` | Group vibe change rejected because cooldown has not expired |
| 403 | `PERMISSION_DENIED` | Operation requires admin rights the caller does not have |
| 423 | `IDENTITY_LOCKED` | Keystore is locked; client must POST `/api/identity/unlock` first |
| 422 | `SEED_PHRASE_INVALID` | Seed phrase supplied during import could not be decoded |
| 413 | `ATTACHMENT_TOO_LARGE` | File exceeds Session file server size limit |
| 500 | `INTERNAL_ERROR` | Unexpected server-side failure |
| 503 | `NETWORK_UNAVAILABLE` | Could not reach the Session onion network |

---

## Global Validation Rules

These rules apply at every layer (frontend, backend Pydantic, database check constraint) unless the entity section overrides them.

| Field type | Rule |
|---|---|
| `sessionId` | Exactly 66 lowercase hex characters; must begin with `05` |
| `displayName` | 1–64 characters; no leading/trailing whitespace |
| `groupName` | 1–64 characters; no leading/trailing whitespace |
| Pagination `limit` | Integer 1–100; default 50 |
| Pagination `before` | ISO 8601 UTC datetime string or integer Unix timestamp (ms) |

---

## Resource: Identity

### Business Rules
- Exactly one identity exists per application instance (single local user).
- The private key is never returned to the frontend under any circumstances.
- The mnemonic is returned **once** at creation time and never stored or surfaced again.
- Before performing any operation, the keystore must be unlocked by providing the passphrase.

---

### API Endpoints — Identity

#### `POST /api/identity/new`
Generate a fresh keypair and create a new identity. Fails if an identity already exists.

**Request body:**
```typescript
{
  passphrase: string;       // Required. Min 8 chars. Used to encrypt the keystore.
  displayName?: string;     // Optional. 1–64 chars.
}
```

**Response `201 Created`:**
```typescript
{
  sessionId: string;        // 66-char hex, 05-prefixed public key
  displayName: string | null;
  mnemonic: string;         // Space-separated seed words — shown ONCE, never stored plaintext
  createdAt: string;        // ISO 8601 UTC
}
```

**Example:**
```json
// POST /api/identity/new
// Request
{ "passphrase": "hunter2hunter2", "displayName": "Alice" }

// Response 201
{
  "sessionId": "057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b",
  "displayName": "Alice",
  "mnemonic": "gels zeal abbey deftly mullet luggage orders lunar coils scenic...",
  "createdAt": "2026-04-04T12:00:00Z"
}
```

**Errors:** `IDENTITY_ALREADY_CREATED` (409), `VALIDATION_ERROR` (400)

---

#### `POST /api/identity/import`
Import an existing identity from a Session seed phrase.

**Request body:**
```typescript
{
  mnemonic: string;         // Required. Space-separated seed words.
  passphrase: string;       // Required. Min 8 chars. New passphrase for local keystore.
  displayName?: string;
}
```

**Response `201 Created`:**
```typescript
{
  sessionId: string;
  displayName: string | null;
  createdAt: string;        // ISO 8601 UTC
  // NOTE: mnemonic is NOT returned; caller already has it
}
```

**Errors:** `IDENTITY_ALREADY_CREATED` (409), `SEED_PHRASE_INVALID` (422), `VALIDATION_ERROR` (400)

---

#### `GET /api/identity`
Return the current identity's public information. Requires unlocked keystore.

**Response `200 OK`:**
```typescript
{
  sessionId: string;
  displayName: string | null;
  personalVibe: VibeId | null;
  createdAt: string;
}
```

**Errors:** `NOT_FOUND` (404) if no identity created yet, `IDENTITY_LOCKED` (423)

---

#### `POST /api/identity/unlock`
Unlock the keystore with the user's passphrase. Must be called after app start before any other endpoint.

**Request body:**
```typescript
{
  passphrase: string;
}
```

**Response `200 OK`:**
```typescript
{ "ok": true }
```

**Errors:** `VALIDATION_ERROR` (400) on wrong passphrase

---

#### `PATCH /api/identity`
Update mutable identity fields.

**Request body (all fields optional; at least one required):**
```typescript
{
  displayName?: string;
  personalVibe?: VibeId | null;   // null clears the personal vibe
}
```

**Response `200 OK`:** Same shape as `GET /api/identity`.

---

### Database — `identities` table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `INTEGER` | PK, AUTOINCREMENT | |
| `session_id` | `TEXT` | NOT NULL, UNIQUE | 66-char hex, `05` prefix |
| `display_name` | `TEXT` | NULL | 1–64 chars enforced in app layer |
| `personal_vibe` | `TEXT` | NULL, CHECK(vibe enum) | See Vibe enums |
| `created_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | Updated by trigger |

> **Note:** The encrypted keystore (private key + Argon2-derived key) is stored as a **separate file on disk** (`keystore.enc`), not in the database. The `identities` table holds only public/display data.

---

## Resource: Contact

### Business Rules
- A contact is any remote Session ID the local user has added or received a message from.
- `accepted = FALSE` means a conversation request is pending (message received from unknown Session ID).
- Contacts are never auto-accepted; the user must explicitly accept a conversation request.
- `displayName` is a user-assigned local nickname — it does not propagate to other users.

---

### API Endpoints — Contact

#### `GET /api/contacts`
List all contacts.

**Query parameters:**
| Param | Type | Default | Description |
|---|---|---|---|
| `accepted` | `boolean` | *(all)* | Filter by acceptance status |

**Response `200 OK`:**
```typescript
{
  contacts: Array<{
    sessionId: string;
    displayName: string | null;
    accepted: boolean;
    createdAt: string;
    updatedAt: string;
  }>;
}
```

---

#### `POST /api/contacts`
Add a contact by Session ID. Creates an accepted contact (user-initiated add).

**Request body:**
```typescript
{
  sessionId: string;          // Required. Must pass Session ID validation.
  displayName?: string;
}
```

**Response `201 Created`:**
```typescript
{
  sessionId: string;
  displayName: string | null;
  accepted: boolean;          // true for user-initiated adds
  createdAt: string;
}
```

**Errors:** `ALREADY_EXISTS` (409), `INVALID_SESSION_ID` (400)

---

#### `PATCH /api/contacts/{sessionId}`
Update a contact (rename, or accept a pending conversation request).

**Path param:** `sessionId` — the contact's Session ID (URL-encoded).

**Request body (all optional; at least one required):**
```typescript
{
  displayName?: string | null;  // null clears the nickname
  accepted?: true;              // Can only transition false → true
}
```

**Response `200 OK`:** Same shape as the contact object above.

**Errors:** `NOT_FOUND` (404), `INVALID_SESSION_ID` (400)

---

#### `DELETE /api/contacts/{sessionId}`
Remove a contact. Does not delete the conversation history.

**Response `204 No Content`**

**Errors:** `NOT_FOUND` (404)

---

### Database — `contacts` table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `INTEGER` | PK, AUTOINCREMENT | |
| `session_id` | `TEXT` | NOT NULL, UNIQUE | FK-like; not a formal FK to allow contacts not yet in identity table |
| `display_name` | `TEXT` | NULL | User-assigned local nickname |
| `accepted` | `INTEGER` | NOT NULL, DEFAULT 0, CHECK(IN(0,1)) | Boolean: 0=pending, 1=accepted |
| `created_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

**Indexes:**
- `contacts(session_id)` — primary lookup
- `contacts(accepted)` — filter pending requests

---

## Resource: Conversation

### Business Rules
- A conversation is either a **DM** (type `DM`) or a **group chat** (type `GROUP`).
- DM conversations are identified by the remote peer's Session ID.
- Group conversations are identified by the group's internal ID.
- `personalVibeOverride` is local-only; it does not affect other participants.
- `groupVibe` is the shared vibe for the group, synced to all members.
- A conversation auto-created by an incoming message from an unknown Session ID has `accepted = FALSE` until the user accepts the conversation request.

---

### API Endpoints — Conversation

#### `GET /api/conversations`
List all conversations, ordered by most recent message.

**Query parameters:**
| Param | Type | Default | Description |
|---|---|---|---|
| `type` | `"DM" \| "GROUP"` | *(all)* | Filter by type |

**Response `200 OK`:**
```typescript
{
  conversations: Array<{
    id: number;
    type: "DM" | "GROUP";
    // For DM:
    contact?: {
      sessionId: string;
      displayName: string | null;
    };
    // For GROUP:
    group?: {
      id: number;
      name: string;
      memberCount: number;
    };
    lastMessage: {
      body: string | null;
      sentAt: string;
      senderSessionId: string;
    } | null;
    unreadCount: number;
    groupVibe: VibeId | null;
    personalVibeOverride: VibeId | null;
    vibeCooldownUntil: string | null;    // ISO 8601 UTC; null if no active cooldown
    accepted: boolean;
    createdAt: string;
    updatedAt: string;
  }>;
}
```

---

#### `GET /api/conversations/{id}/messages`
Retrieve messages for a conversation, newest-first, with cursor-based pagination.

**Path param:** `id` — conversation ID (integer).

**Query parameters:**
| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | `integer` | 50 | 1–100 |
| `before` | `string` | *(latest)* | ISO 8601 UTC datetime; return messages older than this |

**Response `200 OK`:**
```typescript
{
  messages: Array<MessageObject>;     // See Message resource for MessageObject shape
  hasMore: boolean;
  nextBefore: string | null;          // Pass as `before` for the next page; null if no more
}
```

**Errors:** `NOT_FOUND` (404)

---

#### `PATCH /api/conversations/{id}`
Update conversation-level settings for the local user.

**Request body:**
```typescript
{
  personalVibeOverride?: VibeId | null;
  accepted?: true;
}
```

**Response `200 OK`:** Full conversation object (same shape as list item above).

---

### Database — `conversations` table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `INTEGER` | PK, AUTOINCREMENT | |
| `type` | `TEXT` | NOT NULL, CHECK(IN('DM','GROUP')) | |
| `contact_session_id` | `TEXT` | NULL, FK→contacts(session_id) | Set for DM; NULL for GROUP |
| `group_id` | `INTEGER` | NULL, FK→groups(id) | Set for GROUP; NULL for DM |
| `last_message_at` | `DATETIME` | NULL | Updated on each new message |
| `unread_count` | `INTEGER` | NOT NULL, DEFAULT 0 | |
| `group_vibe` | `TEXT` | NULL, CHECK(vibe enum) | Shared group vibe; DMs always NULL |
| `personal_vibe_override` | `TEXT` | NULL, CHECK(vibe enum) | Per-user local override |
| `vibe_changed_at` | `DATETIME` | NULL | Timestamp of last group vibe change |
| `vibe_cooldown_until` | `DATETIME` | NULL | Cooldown expiry; enforced server-side |
| `accepted` | `INTEGER` | NOT NULL, DEFAULT 0, CHECK(IN(0,1)) | |
| `created_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

**Constraints:**
- CHECK: `(type = 'DM' AND contact_session_id IS NOT NULL AND group_id IS NULL) OR (type = 'GROUP' AND group_id IS NOT NULL AND contact_session_id IS NULL)`

**Indexes:**
- `conversations(last_message_at DESC)` — default list ordering
- `conversations(contact_session_id)` — DM lookup by peer
- `conversations(group_id)` — group conversation lookup
- `conversations(accepted)` — filter pending requests

---

## Resource: Message

### Business Rules
- Messages have a `type` that determines which fields are populated.
- `body` is populated for `TEXT` and `SYSTEM` messages; null for others.
- `expiresAt` is populated when the active group vibe is `404` (24-hour TTL from `sentAt`).
- `deliverAfter` is populated when the active group vibe is `SLOW_BURN`.
- `isAnonymous = true` when the active group vibe is `CONFESSIONAL` — the `senderSessionId` must NOT be sent to the frontend in this case.
- `SYSTEM` messages are generated locally (e.g. vibe change notifications) and are never transmitted over the Session network.

---

### API Endpoints — Message

#### `POST /api/messages/send`
Send a message to a conversation.

**Request body:**
```typescript
{
  conversationId: number;         // Required.
  body?: string;                  // Required if no attachmentId. Max 2000 chars (TBD).
  attachmentId?: number;          // ID of a pre-uploaded attachment.
  // Note: type is always TEXT when sent via this endpoint; SYSTEM/GROUP_EVENT are internal.
}
```

**Response `201 Created`:** A `MessageObject` (see below).

**Errors:** `NOT_FOUND` (404) for unknown conversationId, `IDENTITY_LOCKED` (423), `NETWORK_UNAVAILABLE` (503)

---

#### `POST /api/messages/{id}/pin`
Pin a message to protect it from the 404-vibe 24-hour auto-delete. Any group member may pin a message (not admin-only — the escape hatch must be accessible to all). Pinned messages are excluded from the background expiry purge job regardless of `expiresAt`.

**Path param:** `id` — message ID (integer).

**Request body:** *(empty)*

**Response `200 OK`:**
```typescript
{ "id": number; "isPinned": true }
```

**Errors:** `NOT_FOUND` (404)

---

#### `DELETE /api/messages/{id}/pin`
Un-pin a message. If the message has an `expiresAt` in the future, the countdown resumes; if `expiresAt` has already passed, the message is eligible for immediate deletion by the next purge run.

**Response `200 OK`:**
```typescript
{ "id": number; "isPinned": false }
```

**Errors:** `NOT_FOUND` (404)

---

### MessageObject (shared response shape)

```typescript
type MessageObject = {
  id: number;
  conversationId: number;
  senderSessionId: string | null;   // null when isAnonymous = true (CONFESSIONAL vibe)
  body: string | null;
  type: "TEXT" | "ATTACHMENT" | "GROUP_EVENT" | "SYSTEM";
  sentAt: string;                   // ISO 8601 UTC
  receivedAt: string | null;        // null for outgoing messages not yet confirmed
  expiresAt: string | null;         // 404 vibe: sentAt + 24 h; forward-only (see OQ-2 resolution)
  deliverAfter: string | null;      // SLOW_BURN vibe: sentAt + 60 s (fixed)
  isAnonymous: boolean;             // true in CONFESSIONAL vibe
  isSpotlightPinned: boolean;       // true if pinned in SPOTLIGHT vibe
  isPinned: boolean;                // true if user has pinned the message as a 404-escape-hatch
  chorusGroupId: string | null;     // CHORUS vibe: UUID shared by messages within the same 30-second window
  attachment: AttachmentObject | null;
  groupEventType: "MEMBER_JOINED" | "MEMBER_LEFT" | "VIBE_CHANGED" | "GROUP_RENAMED" | null;
  vibeMetadata: {
    activeVibe: VibeId | null;      // Vibe in effect when message was sent (for rendering context)
  } | null;
};
```

---

### Database — `messages` table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `INTEGER` | PK, AUTOINCREMENT | |
| `conversation_id` | `INTEGER` | NOT NULL, FK→conversations(id) | |
| `sender_session_id` | `TEXT` | NULL | NULL for anonymous messages (CONFESSIONAL) |
| `body` | `TEXT` | NULL | Populated for TEXT and SYSTEM types |
| `type` | `TEXT` | NOT NULL, CHECK(IN('TEXT','ATTACHMENT','GROUP_EVENT','SYSTEM')) | |
| `sent_at` | `DATETIME` | NOT NULL | |
| `received_at` | `DATETIME` | NULL | |
| `expires_at` | `DATETIME` | NULL | 404 vibe: `sent_at + 24h` |
| `deliver_after` | `DATETIME` | NULL | SLOW_BURN vibe: `sent_at + delay` |
| `is_anonymous` | `INTEGER` | NOT NULL, DEFAULT 0, CHECK(IN(0,1)) | CONFESSIONAL vibe |
| `is_spotlight_pinned` | `INTEGER` | NOT NULL, DEFAULT 0, CHECK(IN(0,1)) | SPOTLIGHT vibe |
| `is_pinned` | `INTEGER` | NOT NULL, DEFAULT 0, CHECK(IN(0,1)) | 404 escape hatch; purge job skips rows where is_pinned=1 |
| `chorus_group_id` | `TEXT` | NULL | UUID assigned server-side to messages sent within the same 30-second CHORUS window; NULL outside CHORUS vibe |
| `attachment_id` | `INTEGER` | NULL, FK→attachments(id) | |
| `group_event_type` | `TEXT` | NULL, CHECK(IN('MEMBER_JOINED','MEMBER_LEFT','VIBE_CHANGED','GROUP_RENAMED') OR group_event_type IS NULL) | |
| `active_vibe_at_send` | `TEXT` | NULL, CHECK(vibe enum) | Snapshot of vibe when message was created |
| `created_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

**Indexes:**
- `messages(conversation_id, sent_at DESC)` — primary query pattern (paginated message list)
- `messages(expires_at)` — background purge job; partial index `WHERE expires_at IS NOT NULL AND is_pinned = 0`
- `messages(is_spotlight_pinned)` — partial index `WHERE is_spotlight_pinned = 1` for SPOTLIGHT vibe lookup
- `messages(chorus_group_id)` — partial index `WHERE chorus_group_id IS NOT NULL` for CHORUS collage queries

---

## Resource: Group

### Business Rules
- Groups use Session's current group model (not legacy closed groups).
- Only admins can add/remove members or change the group vibe to a behavioral or wildcard vibe.
- Any member can change the group vibe to an aesthetic vibe (subject to cooldown).
- Behavioral and wildcard vibe changes require a frontend confirmation step before the API is called.
- A **5-minute cooldown** applies after any group vibe change (aesthetic or behavioral). The `vibeCooldownUntil` timestamp is set to `now + 5 minutes` and enforced server-side on every `PATCH /api/groups/{id}` that includes a `vibe` field.
- SLOW_BURN delay is **fixed at 60 seconds** — no per-group configuration. This is a compile-time constant in `messaging/delay.py`, not stored in the database.
- When a member leaves, a `GROUP_EVENT / MEMBER_LEFT` system message is broadcast.

---

### API Endpoints — Group

#### `POST /api/groups`
Create a new group.

**Request body:**
```typescript
{
  name: string;                   // Required. 1–64 chars.
  memberSessionIds?: string[];    // Optional initial members (not including self).
}
```

**Response `201 Created`:**
```typescript
{
  id: number;
  groupSessionId: string;         // The Session-network group ID (66-char hex, 05-prefix)
  name: string;
  memberCount: number;
  vibe: VibeId | null;
  vibeCooldownUntil: string | null;
  createdAt: string;
}
```

**Errors:** `INVALID_SESSION_ID` (400) for any member ID, `IDENTITY_LOCKED` (423)

---

#### `GET /api/groups/{id}`
Get group details including members.

**Path param:** `id` — internal group integer ID.

**Response `200 OK`:**
```typescript
{
  id: number;
  groupSessionId: string;
  name: string;
  vibe: VibeId | null;
  vibeCooldownUntil: string | null;
  members: Array<{
    sessionId: string;
    displayName: string | null;       // From local contacts table; null if not in contacts
    isAdmin: boolean;
    joinedAt: string;
  }>;
  createdAt: string;
  updatedAt: string;
}
```

**Errors:** `NOT_FOUND` (404)

---

#### `PATCH /api/groups/{id}`
Update group metadata (admin only).

**Request body (all optional; at least one required):**
```typescript
{
  name?: string;
  vibe?: VibeId | null;     // null clears the group vibe
}
```

**Response `200 OK`:** Full group object (same shape as GET).

**Errors:** `NOT_FOUND` (404), `PERMISSION_DENIED` (403), `VIBE_COOLDOWN_ACTIVE` (409)

**Example — behavioral vibe change (frontend must confirm before calling):**
```json
// PATCH /api/groups/7
{ "vibe": "SLOW_BURN" }

// Response 200
{
  "id": 7,
  "groupSessionId": "05abc...",
  "name": "Night Owls",
  "vibe": "SLOW_BURN",
  "vibeCooldownUntil": "2026-04-04T13:00:00Z",
  ...
}
```

---

#### `POST /api/groups/{id}/members`
Add one or more members (admin only).

**Request body:**
```typescript
{
  sessionIds: string[];     // Required. 1–N Session IDs.
}
```

**Response `200 OK`:** Updated group object.

**Errors:** `PERMISSION_DENIED` (403), `INVALID_SESSION_ID` (400), `ALREADY_EXISTS` (409)

---

#### `DELETE /api/groups/{id}/members/{sessionId}`
Remove a member (admin only; cannot remove self via this endpoint).

**Response `204 No Content`**

**Errors:** `PERMISSION_DENIED` (403), `NOT_FOUND` (404)

---

#### `POST /api/groups/{id}/leave`
Leave the group. Broadcasts a MEMBER_LEFT group event.

**Request body:** *(empty)*

**Response `200 OK`:**
```typescript
{ "ok": true }
```

---

### Database — `groups` table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `INTEGER` | PK, AUTOINCREMENT | Internal ID |
| `group_session_id` | `TEXT` | NOT NULL, UNIQUE | Session-network group ID (66-char hex) |
| `name` | `TEXT` | NOT NULL | 1–64 chars |
| `created_by_session_id` | `TEXT` | NOT NULL | Session ID of creator |
| `vibe` | `TEXT` | NULL, CHECK(vibe enum) | Current group vibe |
| `vibe_changed_at` | `DATETIME` | NULL | |
| `vibe_cooldown_until` | `DATETIME` | NULL | Cooldown expiry; set to `now + 5 min` on every vibe change |
| `created_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

> **Note:** `slow_burn_delay_seconds` is **not** a column. The 60-second delay is a constant defined in `messaging/delay.py:SLOW_BURN_DELAY_SECONDS = 60`.

### Database — `group_members` table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `INTEGER` | PK, AUTOINCREMENT | |
| `group_id` | `INTEGER` | NOT NULL, FK→groups(id) ON DELETE CASCADE | |
| `session_id` | `TEXT` | NOT NULL | Member's Session ID |
| `is_admin` | `INTEGER` | NOT NULL, DEFAULT 0, CHECK(IN(0,1)) | |
| `joined_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

**Constraints:**
- UNIQUE(`group_id`, `session_id`)

**Indexes:**
- `group_members(group_id)` — list members for a group
- `group_members(session_id)` — find all groups a user belongs to

---

## Resource: Attachment

### Business Rules
- Files are encrypted **before** upload using AES-256-CBC + HMAC-SHA256 per Session spec.
- The upload endpoint first encrypts locally, uploads to the Session file server, then stores the pointer URL and keys in the database.
- The `encryptionKey` and `hmacKey` are never returned to the frontend; decryption happens server-side.
- `status` drives the progress indicator in the UI.
- Session file size limits are enforced; the exact limit must be sourced from the protocol docs (see open questions).

---

### API Endpoints — Attachment

#### `POST /api/attachments/upload`
Upload a file. Uses `multipart/form-data`.

**Request fields:**
| Field | Type | Notes |
|---|---|---|
| `file` | `binary` | Required. The raw file bytes. |
| `conversationId` | `integer` | Required. The target conversation. |

**Response `201 Created`:**
```typescript
type AttachmentObject = {
  id: number;
  fileName: string;
  fileSize: number;           // bytes
  mimeType: string;
  status: AttachmentStatus;
  createdAt: string;
};
```

**Errors:** `ATTACHMENT_TOO_LARGE` (413), `NOT_FOUND` (404) for unknown conversation

**Example:**
```json
// POST /api/attachments/upload (multipart)
// Response 201
{
  "id": 42,
  "fileName": "photo.jpg",
  "fileSize": 204800,
  "mimeType": "image/jpeg",
  "status": "UPLOADED",
  "createdAt": "2026-04-04T12:05:00Z"
}
```

---

#### `GET /api/attachments/{id}`
Download and decrypt an attachment. Returns the raw decrypted file bytes.

**Response `200 OK`:** Binary file stream. `Content-Type` header set to the stored MIME type. `Content-Disposition: attachment; filename="{fileName}"`.

**Errors:** `NOT_FOUND` (404), `NETWORK_UNAVAILABLE` (503)

---

### Database — `attachments` table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `INTEGER` | PK, AUTOINCREMENT | |
| `message_id` | `INTEGER` | NULL, FK→messages(id) | NULL while upload is in progress |
| `file_name` | `TEXT` | NOT NULL | Original filename |
| `file_size` | `INTEGER` | NOT NULL | Bytes |
| `mime_type` | `TEXT` | NOT NULL | |
| `upload_url` | `TEXT` | NULL | Pointer URL on Session file server; NULL until upload completes |
| `encryption_key` | `BLOB` | NULL | AES-256 key; stored encrypted by SQLCipher — never exposed via API |
| `hmac_key` | `BLOB` | NULL | HMAC-SHA256 key; same protection |
| `local_cache_path` | `TEXT` | NULL | Absolute path to local decrypted cache; NULL if not cached |
| `status` | `TEXT` | NOT NULL, DEFAULT 'PENDING', CHECK(status enum) | |
| `created_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | `DATETIME` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

**Indexes:**
- `attachments(message_id)` — join from messages
- `attachments(status)` — background jobs for retry/cleanup

---

## Enums & Constants

### `VibeId`

```typescript
type VibeId =
  // Aesthetic vibes (personal or group)
  | "CAMPFIRE"
  | "NEON"
  | "LIBRARY"
  | "VOID"
  | "SUNRISE"
  // Behavioral vibes (group-level only)
  | "404"
  | "CONFESSIONAL"
  | "SLOW_BURN"
  | "CHORUS"
  | "SPOTLIGHT"
  | "ECHO"
  // Wildcard vibes (group-level only)
  | "SCRAMBLE";
```

**Vibe classification (for permission checks):**

| `VibeId` | Category | Group-level | Personal-level |
|---|---|---|---|
| `CAMPFIRE` | Aesthetic | ✓ | ✓ |
| `NEON` | Aesthetic | ✓ | ✓ |
| `LIBRARY` | Aesthetic | ✓ | ✓ |
| `VOID` | Aesthetic | ✓ | ✓ |
| `SUNRISE` | Aesthetic | ✓ | ✓ |
| `404` | Behavioral | ✓ | ✗ |
| `CONFESSIONAL` | Behavioral | ✓ | ✗ |
| `SLOW_BURN` | Behavioral | ✓ | ✗ |
| `CHORUS` | Behavioral | ✓ | ✗ |
| `SPOTLIGHT` | Behavioral | ✓ | ✗ |
| `ECHO` | Behavioral | ✓ | ✗ |
| `SCRAMBLE` | Wildcard | ✓ | ✗ |

> **Backend rule:** Any attempt to set a behavioral or wildcard vibe as a personal vibe must be rejected with `VALIDATION_ERROR`. Any attempt to set a behavioral/wildcard group vibe without admin rights must be rejected with `PERMISSION_DENIED`.

---

### `AttachmentStatus`

```typescript
type AttachmentStatus = "PENDING" | "UPLOADING" | "UPLOADED" | "DOWNLOADING" | "DOWNLOADED" | "FAILED";
```

---

### `MessageType`

```typescript
type MessageType = "TEXT" | "ATTACHMENT" | "GROUP_EVENT" | "SYSTEM";
```

---

### `GroupEventType`

```typescript
type GroupEventType = "MEMBER_JOINED" | "MEMBER_LEFT" | "VIBE_CHANGED" | "GROUP_RENAMED";
```

---

### `ConversationType`

```typescript
type ConversationType = "DM" | "GROUP";
```

---

## WebSocket Contract

**Endpoint:** `ws://localhost:{PORT}/ws`

The WebSocket connection streams real-time events to the frontend. The client connects once on app load and maintains the connection.

### Message envelope

All events from server → client use:
```typescript
type WSEvent = {
  event: WSEventType;
  payload: unknown;     // Shape varies by event type; see below
};
```

### Event Types

#### `message_received`
A new message arrived (from the onion network poller or sent locally).
```typescript
payload: MessageObject    // Same shape as REST MessageObject
```

#### `attachment_progress`
Upload or download progress update.
```typescript
payload: {
  attachmentId: number;
  status: AttachmentStatus;
  progressPercent: number;    // 0–100
}
```

#### `vibe_changed`
The group vibe was changed by a member.
```typescript
payload: {
  conversationId: number;
  newVibe: VibeId | null;
  changedBySessionId: string;
  cooldownUntil: string;          // ISO 8601 UTC
  isBehavioral: boolean;          // Frontend uses this to decide notification prominence
}
```

#### `conversation_request`
A message arrived from an unknown Session ID (pending conversation request).
```typescript
payload: {
  conversationId: number;
  fromSessionId: string;
}
```

#### `identity_locked`
The keystore lock timeout expired. Frontend should show unlock prompt.
```typescript
payload: {}
```

---

## Field Mapping Table

| API field (camelCase) | Python model field (snake_case) | DB column (snake_case) | Table |
|---|---|---|---|
| `sessionId` | `session_id` | `session_id` | `identities`, `contacts`, `group_members` |
| `displayName` | `display_name` | `display_name` | `identities`, `contacts` |
| `personalVibe` | `personal_vibe` | `personal_vibe` | `identities` |
| `conversationId` | `conversation_id` | `id` | `conversations` |
| `contactSessionId` | `contact_session_id` | `contact_session_id` | `conversations` |
| `groupId` | `group_id` | `group_id` | `conversations` |
| `lastMessageAt` | `last_message_at` | `last_message_at` | `conversations` |
| `unreadCount` | `unread_count` | `unread_count` | `conversations` |
| `groupVibe` | `group_vibe` | `group_vibe` | `conversations` |
| `personalVibeOverride` | `personal_vibe_override` | `personal_vibe_override` | `conversations` |
| `vibeCooldownUntil` | `vibe_cooldown_until` | `vibe_cooldown_until` | `conversations`, `groups` |
| `senderSessionId` | `sender_session_id` | `sender_session_id` | `messages` |
| `sentAt` | `sent_at` | `sent_at` | `messages` |
| `receivedAt` | `received_at` | `received_at` | `messages` |
| `expiresAt` | `expires_at` | `expires_at` | `messages` |
| `deliverAfter` | `deliver_after` | `deliver_after` | `messages` |
| `isAnonymous` | `is_anonymous` | `is_anonymous` | `messages` |
| `isSpotlightPinned` | `is_spotlight_pinned` | `is_spotlight_pinned` | `messages` |
| `attachmentId` | `attachment_id` | `attachment_id` | `messages` |
| `groupEventType` | `group_event_type` | `group_event_type` | `messages` |
| `activeVibeAtSend` | `active_vibe_at_send` | `active_vibe_at_send` | `messages` |
| `isPinned` | `is_pinned` | `is_pinned` | `messages` |
| `chorusGroupId` | `chorus_group_id` | `chorus_group_id` | `messages` |
| `groupSessionId` | `group_session_id` | `group_session_id` | `groups` |
| `createdBySessionId` | `created_by_session_id` | `created_by_session_id` | `groups` |
| `isAdmin` | `is_admin` | `is_admin` | `group_members` |
| `joinedAt` | `joined_at` | `joined_at` | `group_members` |
| `fileName` | `file_name` | `file_name` | `attachments` |
| `fileSize` | `file_size` | `file_size` | `attachments` |
| `mimeType` | `mime_type` | `mime_type` | `attachments` |
| `uploadUrl` | `upload_url` | `upload_url` | `attachments` |
| `localCachePath` | `local_cache_path` | `local_cache_path` | `attachments` |
| `createdAt` | `created_at` | `created_at` | *(all tables)* |
| `updatedAt` | `updated_at` | `updated_at` | *(most tables)* |

---

## Validation Rules (Canonical)

| Rule | API layer (Pydantic) | Frontend (pre-submit) | DB layer |
|---|---|---|---|
| Session ID: 66 hex chars, `05` prefix | `constr(regex=r'^05[0-9a-f]{64}$')` | Regex before any network call | `CHECK(length(session_id)=66 AND session_id LIKE '05%')` |
| `displayName` / `groupName`: 1–64 chars, no leading/trailing whitespace | `constr(min_length=1, max_length=64, strip_whitespace=True)` | Inline validation | `CHECK(length(trim(col)) BETWEEN 1 AND 64)` |
| Passphrase: min 8 chars | `constr(min_length=8)` | Inline validation | Not stored in DB |
| `limit` pagination param: 1–100 | `conint(ge=1, le=100)` | Not applicable | Not applicable |
| `personalVibe` must be aesthetic category | Custom validator | Dropdown restricted | `CHECK(col IN (aesthetic values) OR col IS NULL)` |
| `groupVibe` can be any `VibeId` | Enum validator | Enum dropdown | `CHECK(col IN (all vibe values) OR col IS NULL)` |
| `fileSize` 1–10,485,760 bytes | Auto from multipart; 413 if exceeded | File picker shows size warning | `CHECK(file_size > 0)` |
| `body` on TEXT messages: 1–2000 chars | `constr(min_length=1, max_length=2000)` | Character counter (show at 1800) | Not enforced at DB level |
| `is_anonymous` must be 0 when vibe is not CONFESSIONAL | Application logic | Not applicable | Not enforced at DB level (application invariant) |

---

## Resolved Decisions

All open questions from v0.1.0 are now closed. The table below records each decision and its rationale so the reasoning is auditable.

### Resolved (formerly open) questions

| # | Decision | Rationale |
|---|---|---|
| OQ-1 | **Vibe cooldown: 5 minutes.** `vibe_cooldown_until = now + 300s` on every vibe change, aesthetic or behavioral. | 5 min prevents rapid-switching abuse without over-punishing accidental changes. A tiered system adds complexity with no MVP benefit. |
| OQ-2 | **404 vibe — forward-only.** Activating 404 sets `expires_at` only on messages created *after* activation. Pre-existing messages are unaffected. | Retroactive deletion is surprising and destructive. Forward-only is the least-surprise default. |
| OQ-3 | **404 vibe — countdown continues on exit.** Messages with an `expires_at` retain it when the vibe changes; the purge job deletes them on schedule regardless. | Prevents exploiting deactivation as a save mechanism. The commitment is made at send time. |
| OQ-4 | **Pin escape hatch — yes.** `is_pinned BOOLEAN` added to `messages`. Purge job skips `is_pinned = 1` rows. Any member may pin. `POST /api/messages/{id}/pin` and `DELETE /api/messages/{id}/pin` added. Distinct from `is_spotlight_pinned`. | Every user needs an opt-out for content they own. Admin-only would be too restrictive for a safety feature. |
| OQ-5 | **Chorus grouping window: 30 seconds.** Messages within 30 s of each other share a `chorus_group_id` UUID assigned server-side when the first message of a batch is stored. | 30 s captures natural conversational bursts without merging separate exchanges. UUID approach is lightweight and join-free. |
| OQ-6 | **Slow Burn delay: fixed 60 seconds.** Constant `SLOW_BURN_DELAY_SECONDS = 60` in `messaging/delay.py`. No DB column. | Fixed keeps the feature simple and predictable for the MVP. Can be promoted to a group setting without a schema change. |
| OQ-7 | **File size limit: 10,485,760 bytes (10 MiB).** Constant `MAX_ATTACHMENT_BYTES = 10_485_760` in `attachments/upload.py`. Enforced before encryption. | Session FSv2 enforces 10 MiB per the session.js reference implementation (`src/attachments/`). |
| OQ-8 | **Default port: 8000 (FastAPI).** Vite dev server: 5173. Both overridable via `WHISPER_PORT` / `VITE_PORT` env vars. Vite proxies `/api` and `/ws` to 8000 in dev. | 8000 is the uvicorn default. Env-var override satisfies cross-platform portability. |
| OQ-9 | **Message body max: 2,000 characters** (confirmed). Frontend shows counter from 1,800. | Consistent with common messaging conventions (e.g. Discord). Sufficient for all expected use. |
| OQ-10 | **Keystore idle timeout: 15 minutes.** Only user-initiated API calls reset the timer; the polling loop does not. `identity_locked` WS event fires on expiry. | 15 min balances security and usability for a local app. Polling must not reset the timer or the keystore would never lock automatically. |
| OQ-11 | **SCRAMBLE: client-side only.** Frontend picks a random aesthetic vibe every 30–120 s. DB remains `vibe = 'SCRAMBLE'`. No WS event needed. | Pure display-layer feature; no server coordination required. Keeps the WS event model clean. |
| OQ-12 | **CHORUS is behavioral (admin-only to set).** `chorus_group_id` tagging runs in the Messaging Layer and alters how messages are stored for all members. | Server behaviour change → behavioral classification. Admin-only prevents non-admins from silently reorganising conversation layout. |

---

## Standing Assumptions

| # | Assumption | Basis |
|---|---|---|
| A-1 | Single `identities` row per app instance; no multi-account support. | "No multi-device sync" and "local-only tool" in CONTEXT.md. |
| A-2 | Keystore unlock is session-scoped (in-memory); no token issued. All endpoints implicitly require an unlocked keystore. | Localhost-only app. |
| A-3 | `encryption_key` and `hmac_key` protected by SQLCipher at rest; never exposed via API. | CONTEXT.md: "Never store private keys or passphrases in plaintext." |
| A-4 | DM conversations: `groupVibe` is always NULL; only `personalVibeOverride` applies. | CONTEXT.md: behavioral vibes are group-only. |
| A-5 | CONFESSIONAL: `sender_session_id` stored in DB for protocol integrity; API returns `null` when `is_anonymous = 1`. | Privacy intent in CONTEXT.md. |
| A-6 | `mnemonic` returned only from `POST /api/identity/new`; never stored in DB or returned elsewhere. | CONTEXT.md Layer 1. |
| A-7 | Hard deletes throughout. 404 TTL enforced by background purge job. | No `deleted_at` pattern specified; simpler for a single-user local app. |
| A-8 | Cursor-based pagination (`before` timestamp) for messages. | Prevents duplicate rows across pages when real-time inserts occur. |
| A-9 | ECHO vibe is a pure frontend concern (`sentAt` drives opacity fade). No backend fields required. | CONTEXT.md: "ghostly but never deleted" — visual effect only. |
