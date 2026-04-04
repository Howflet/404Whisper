# 404Whisper — GitHub Copilot Project Context

> Place this file at `.github/copilot-instructions.md` in your repository root so Copilot automatically uses it as context for all suggestions in this project.

---

## What This Project Is

**404Whisper** is a general-purpose, platform-agnostic messaging application built on the [Session](https://getsession.org) decentralised messaging protocol. It allows users to send and receive end-to-end encrypted messages, participate in group chats, and share file attachments — with no phone number, email, or centralised account required. The UI is browser-based, served locally. Users share their Session ID with each other out-of-band (copy-paste) — there is no in-app user search or discovery.

The project is written in **Python 3.9+** and implements the Session network protocol natively in Python, using the open-source [session.js](https://github.com/sessionjs/client) library as a protocol reference. It does **not** wrap or depend on the official Session desktop/mobile clients, Node.js, Bun, or any non-Python runtime.

---

## Goals & Non-Goals

### Goals
- Pure Python implementation, installable via `pip install 404whisper`
- Runs on Linux, macOS, Windows, and BSD — any system with Python 3.9+
- Browser-based UI served locally via a FastAPI backend; no installation of a GUI toolkit required
- No phone number or email required to create an account
- All messages routed via Session's onion network (end-to-end encrypted)
- Local data stored in an encrypted SQLite database
- Clean separation between protocol logic and UI logic

### Non-Goals (deferred to future versions)
- Voice or video calling
- Read receipts or disappearing messages
- Multi-device sync
- Open Groups (SOGS)
- In-app user search or discovery — users share Session IDs out-of-band (copy-paste) only
- QR code sharing (deferred)
- Push notifications
- Native GUI desktop wrapper (the web frontend covers this use case)
- Exposing the API on a non-localhost interface (this is a local-only tool)
- Scripting / bot API

---

## Technology Stack

| Concern | Technology |
|---|---|
| Language | Python 3.9+ |
| Cryptographic primitives | PyNaCl (libsodium bindings) + `cryptography` package |
| HTTP client | `httpx` (async-capable) |
| Message serialisation | `protobuf` (Google Protocol Buffers) |
| Local storage | `sqlite3` (stdlib) + `sqlcipher3` for encryption at rest |
| Async runtime | `asyncio` (Python stdlib) |
| Backend API server | `FastAPI` + `uvicorn` (async HTTP + WebSocket server) |
| Frontend | `React 18` + `Vite` (browser-based UI) |
| Real-time transport | WebSockets (via FastAPI `websockets` support) |
| Protocol reference | session.js (MIT licensed, read-only reference) |

---

## Architecture — Eight Layers

The codebase is structured as eight discrete layers. Each has a single responsibility. Do not mix concerns across layers.

```
┌─────────────────────────────────┐
│  8. Web Interface Layer         │  React + Vite frontend / FastAPI server
├─────────────────────────────────┤
│  7. Storage Layer               │  Encrypted SQLite (sqlcipher3)
├─────────────────────────────────┤
│  6. Attachment Layer            │  File encrypt/upload/download/decrypt
├─────────────────────────────────┤
│  5. Group Management Layer      │  Group creation, members, key distribution
├─────────────────────────────────┤
│  4. Messaging Layer             │  Protobuf encode/decode, send, poll, receive
├─────────────────────────────────┤
│  3. Network Layer               │  Onion requests, node discovery, swarm lookup
├─────────────────────────────────┤
│  2. Cryptography Layer          │  X25519, Ed25519, XSalsa20-Poly1305, onion packets
├─────────────────────────────────┤
│  1. Identity & Auth Layer       │  Keypair gen, mnemonic, keystore, passphrase
└─────────────────────────────────┘
```

### Layer Details

**1. Identity & Auth Layer** (`404whisper/identity/`)
- Generates X25519/Ed25519 keypairs
- Encodes/decodes Session mnemonic seed phrases using Session's custom word list (not BIP39)
- Stores the private key encrypted on disk, protected by a user passphrase (use Argon2 KDF)
- Derives the Session ID (the user's public key, hex-encoded, prefixed with `05`)
- Handles first-run flow: generate new identity OR import from seed phrase

**2. Cryptography Layer** (`404whisper/crypto/`)
- X25519 Diffie-Hellman key exchange (via PyNaCl)
- Ed25519 signing and verification (via PyNaCl)
- XSalsa20-Poly1305 symmetric encryption/decryption (via PyNaCl)
- Onion packet construction: three nested encryption layers, one per Service Node
- All functions must be pure and independently unit-testable
- Validate all outputs against known test vectors from session.js

**3. Network Layer** (`404whisper/network/`)
- Fetch and cache the active Service Node list with their public keys
- Swarm lookup: given a Session ID, determine which swarm stores their messages
- Onion request dispatch: wrap a payload in three layers and send via HTTPS
- Handle network failures gracefully with exponential backoff retry
- No UI calls — emit events or return results only

**4. Messaging Layer** (`404whisper/messaging/`)
- Compose outgoing messages using protobuf schema from Session's open-source repos
- Parse and deserialise incoming protobuf-encoded messages
- Async polling loop: query own swarm on a configurable interval
- Handle message types: text, attachment pointer, group event, delivery receipt
- Conversation request handling: messages from unknown Session IDs require acceptance

**5. Group Management Layer** (`404whisper/groups/`)
- Target Session's current group model (not legacy closed groups)
- Group creation, name setting, member invite by Session ID
- Admin permission enforcement (only admins can add/remove members)
- Group key distribution to members
- Leave group flow with system message broadcast

**6. Attachment Layer** (`404whisper/attachments/`)
- Encrypt file client-side before upload (AES-256-CBC + HMAC-SHA256 per Session spec)
- Upload encrypted file to Session file server, receive a pointer URL
- Include pointer in outgoing message payload
- Download and decrypt incoming attachment files
- Enforce Session file size limits — surface a clear error if exceeded
- Show upload/download progress in the TUI

**7. Storage Layer** (`404whisper/storage/`)
- Single encrypted SQLite database per identity
- Schema: `identities`, `contacts`, `conversations`, `messages`, `groups`, `group_members`, `attachments`
- All reads/writes async
- Never store private keys or passphrases in plaintext anywhere in this layer

**8. Web Interface Layer** (`404whisper/api/` + `frontend/`)
- FastAPI application (`404whisper/api/`) exposes a REST + WebSocket API consumed exclusively by the React frontend
- React + Vite frontend (`frontend/`) is a standalone SPA served by FastAPI's static file handler in production, and by the Vite dev server during development
- WebSocket endpoint streams incoming messages to the browser in real time — no polling in the UI
- REST endpoints cover: identity setup, contact management, conversation list, send message, group operations, attachment upload/download
- All FastAPI route handlers must be `async`; no blocking calls on the event loop
- The frontend communicates only with `localhost` — this is not a networked web service
- Views: conversation list, active chat, onboarding/setup flow, group creation modal, attachment progress indicator
- Every input that accepts a Session ID must validate the format client-side (66 hex chars, `05` prefix) and display a clear inline error if invalid — no network call should be made with a malformed ID
- The user's own Session ID must be prominently displayed and one-click copyable from the UI (e.g. in a profile/settings panel) so they can share it out-of-band

---

## Vibe Mode

Vibe Mode allows users to change the visual theme and, in some cases, the behaviour of group chats. Vibes are static presets — they do not shift dynamically.

### Personal vs. Group Vibes

- Any user can set a **personal vibe** (affects only their own view) or a **group vibe** (affects everyone in the chat).
- The settings panel exposes two sections: **"My Vibe"** and **"Group Vibe"**.
- **Aesthetic vibes** (visual-only) can be applied at both the personal and group level.
- **Behavioral vibes** (those that change chat functionality — e.g. 404, Confessional, Slow Burn) can only be applied at the group level, since they change how the space works for everyone.
- When a user has a personal vibe override active, a small indicator shows the current group vibe so they remain aware of the shared experience.

### Group Vibe Change Rules

- When anyone changes the group vibe, a subtle system message appears in the chat (e.g. `"the vibe shifted to Neon"`).
- For **behavioral vibe changes**, the notification must be more prominent (highlighted banner or brief modal) due to functional consequences.
- A **cooldown timer** (exact duration TBD — see open questions) applies after any group vibe change to prevent rapid switching.
- Behavioral vibe changes require a **confirmation step** before being applied.

### Vibe Roster

#### Aesthetic Vibes

| Vibe | Palette & Feel | Notes |
|---|---|---|
| **Campfire** | Warm oranges, deep browns; soft rounded fonts; subtle background flicker/glow | Signals "we're just hanging out" |
| **Neon** | Electric pinks, cyans, black; sharp fonts, high contrast | Energetic, loud, buzzing |
| **Library** | Muted tones, serif fonts, paper-like textures | Quiet, thoughtful, academic |
| **Void** | Near-black background, minimal contrast, sparse | Underground, stripped-back |
| **Sunrise** | Soft pastels, warm-to-cool gradients | Optimistic and calm; good default or "fresh start" vibe |

#### Behavioral Vibes

| Vibe | Behaviour | Visual Aesthetic |
|---|---|---|
| **404** | Messages auto-delete after 24 hours | Glitchy, degraded, ephemeral — must clearly signal temporariness |
| **Confessional** | All anonymous identifiers, handles, and avatars hidden; pure unattributed text | Dark, intimate; group level only |
| **Slow Burn** | ~60-second message delivery delay; discourages rapid-fire chat | Languid — amber tones, slow fade-in on message appearance |
| **Chorus** | Messages sent within a short time window grouped and displayed simultaneously as a collage/mosaic | Emphasises collective voice over individual posts |
| **Spotlight** | One message pinned at the top as "the moment"; community rotates spotlight via reactions | Theatrical — dark background, literal highlight on featured message; suits AMAs and storytelling |
| **Echo** | Messages slowly fade in opacity over time — ghostly but never deleted; opposite of 404 | Layered, archaeological feel |

#### Wildcard Vibes

| Vibe | Behaviour |
|---|---|
| **Scramble** | Visual theme randomises on a timer (exact interval TBD); the community never settles into one look; suits chaotic or meme-heavy groups |

### Open Questions

These decisions are unresolved and must be settled before implementation of the affected vibes:

- **Cooldown duration** — 5 minutes or 10 minutes after a group vibe change?
- **404 — retroactive vs. forward-only** — when switching into 404, does the 24-hour countdown apply to existing messages or only new ones?
- **404 — switching out** — when leaving 404 mode, do messages with remaining countdown become permanent, or does the countdown continue until expiry?
- **404 — save escape hatch** — should users be able to save/pin a message before it is deleted if someone else activates 404?
- **Chorus — grouping window** — what is the right time window for treating messages as simultaneous?
- **Slow Burn — delay duration** — fixed at 60 seconds, or should it be configurable?

### Implementation Notes

- Vibe state (group vibe + per-user personal override) must be stored in the `conversations` / `groups` schema and synced via the WebSocket layer.
- The React frontend applies the active vibe as a top-level CSS class or Tailwind data attribute on the chat container — all vibe-specific styles are scoped to that class, keeping vibe logic out of component logic.
- Behavioral vibe logic (message TTL, delivery delay, anonymisation, grouping) belongs in the **Messaging Layer** (`404whisper/messaging/`) and is exposed to the frontend as metadata on message objects — the UI renders consequences, it does not enforce them.
- The backend must validate that behavioral vibe changes come with a group-level write permission check.

---

## The Session Protocol — Key Concepts

Copilot should understand these concepts when suggesting code in this project:

**Session ID**
A user's identity is their public key. A Session ID looks like:
`057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b`
It is the X25519 public key, hex-encoded, with a `05` prefix.

Users share their Session ID with each other entirely out-of-band — copy-paste is the only supported method. There is no in-app search, username lookup, or QR code. Every UI surface that asks for a recipient (new DM, add group member) must accept a raw Session ID string and validate that it is well-formed (66 hex characters, `05` prefix) before submitting.

**Mnemonic / Seed Phrase**
Session uses its own custom word list (not BIP39). A seed phrase encodes the 32-byte private key as a sequence of human-readable words. The encode/decode logic must match Session's implementation exactly.

**Service Nodes & Swarms**
The network consists of community-operated Service Nodes. Nodes are grouped into swarms of ~5–7 nodes. Each Session ID maps to a specific swarm responsible for storing that user's messages. To deliver a message, you send it to the recipient's swarm.

**Onion Routing**
All requests to the network are wrapped in three nested layers of encryption — one per routing node — so no single node knows both sender identity and destination. The outermost layer is for the first node, which strips its layer and forwards; and so on. This is Session's core privacy mechanism.

**Protobuf Encoding**
Message payloads are serialised using Protocol Buffers. The `.proto` schema definitions are available in Session's open-source repositories and must be compiled using the Python `protobuf` package.

**Polling**
There is no persistent connection. The client periodically polls its own swarm to retrieve stored messages. Polling interval should be adaptive (shorter when the app is in active use, longer when idle).

---

## Protocol Reference — session.js

The session.js library (`@session.js/client`, MIT licence) is used as the primary protocol reference. When implementing any protocol behaviour, cross-reference the equivalent module in session.js:

| What we're implementing | session.js reference module |
|---|---|
| Mnemonic encode/decode | `@session.js/mnemonic` |
| Keypair derivation | `src/crypto/` |
| Service node discovery | `src/network/` |
| Swarm lookup | `src/network/` |
| Onion request construction | `src/crypto/onion` |
| Protobuf message encoding | `src/messages/` |
| Send message | `src/session.ts` → `sendMessage()` |
| Poll & receive | `src/polling/` |
| Attachment upload/download | `src/attachments/` |
| Group protocol | `src/groups/` |

session.js source: https://github.com/sessionjs/client
session.js docs: https://sessionjs.github.io/docs/

---

## Suggested Project Structure

```
404whisper/
├── __init__.py
├── main.py                 # Entry point — starts uvicorn, opens browser
├── identity/
│   ├── __init__.py
│   ├── keypair.py          # Keypair generation and derivation
│   ├── mnemonic.py         # Seed phrase encode/decode
│   └── keystore.py         # Encrypted key storage
├── crypto/
│   ├── __init__.py
│   ├── primitives.py       # X25519, Ed25519, XSalsa20
│   └── onion.py            # Onion packet construction
├── network/
│   ├── __init__.py
│   ├── nodes.py            # Service node discovery and caching
│   ├── swarm.py            # Swarm lookup
│   └── request.py          # Onion request dispatch (httpx)
├── messaging/
│   ├── __init__.py
│   ├── proto/              # Compiled protobuf definitions
│   ├── compose.py          # Outgoing message construction
│   ├── parse.py            # Incoming message parsing
│   └── poll.py             # Async polling loop
├── groups/
│   ├── __init__.py
│   ├── create.py
│   └── members.py
├── attachments/
│   ├── __init__.py
│   ├── upload.py
│   └── download.py
├── storage/
│   ├── __init__.py
│   ├── db.py               # Database connection and schema init
│   └── queries.py          # All read/write queries
└── api/
    ├── __init__.py
    ├── app.py              # FastAPI application root, lifespan, static file mount
    ├── ws.py               # WebSocket endpoint — streams messages to frontend
    └── routes/
        ├── identity.py     # POST /api/identity/new, /api/identity/import
        ├── conversations.py# GET /api/conversations, GET /api/conversations/{id}/messages
        ├── messages.py     # POST /api/messages/send
        ├── contacts.py     # GET/POST /api/contacts
        ├── groups.py       # Group CRUD endpoints
        └── attachments.py  # POST /api/attachments/upload, GET /api/attachments/{id}
frontend/
├── package.json
├── vite.config.ts
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── api/
    │   ├── client.ts       # Typed fetch wrappers for all REST endpoints
    │   └── socket.ts       # WebSocket client with auto-reconnect
    ├── views/
    │   ├── Setup.tsx        # Onboarding flow (new identity or import)
    │   ├── ConversationList.tsx
    │   ├── ChatView.tsx
    │   └── GroupCreate.tsx
    └── components/
        ├── MessageBubble.tsx
        └── AttachmentProgress.tsx
tests/
├── test_mnemonic.py
├── test_keypair.py
├── test_crypto_primitives.py
├── test_onion.py
├── test_storage.py
└── test_api.py             # FastAPI route tests via httpx AsyncClient
```

---

## Coding Conventions

- **Python 3.9+** — use type hints everywhere (`from __future__ import annotations` at top of each file)
- **async/await** throughout — all network and disk operations must be async
- **No side effects in crypto functions** — pure input/output, no global state
- **Errors** — use custom exception classes defined per layer (e.g. `NetworkError`, `DecryptionError`, `StorageError`)
- **Tests** — every cryptographic function must have a corresponding unit test validating against a known test vector
- **No hardcoded secrets** — never commit private keys, passphrases, or test Session IDs that correspond to real accounts
- **Docstrings** — all public functions must have a docstring explaining parameters, return value, and any exceptions raised
- **Logging** — use Python's `logging` module, never `print()` in library code
- **API/frontend boundary** — the React frontend is the only consumer of the FastAPI layer; do not add direct calls from protocol layers into the API layer
- **Frontend language** — TypeScript only, no plain `.js` files; keep API types in sync with FastAPI response models (use Pydantic schemas as the source of truth)

---

## Build Order (Current Phase)

Development proceeds bottom-up through the architecture layers. The current focus is:

**Phase 1 — Identity & Cryptography (active)**
1. `identity/mnemonic.py` — port Session's mnemonic word list and encode/decode logic from session.js
2. `identity/keypair.py` — derive X25519/Ed25519 keypair from seed using PyNaCl
3. `crypto/primitives.py` — implement core crypto operations
4. `identity/keystore.py` — encrypted local storage for the private key

Do not begin Phase 2 (Network) until Phase 1 functions produce outputs that validate against session.js test vectors.

---

## Key External Resources

| Resource | URL |
|---|---|
| session.js source (GitHub mirror) | https://github.com/sessionjs/client |
| session.js documentation | https://sessionjs.github.io/docs/ |
| libsession-util (official C++ crypto lib) | https://github.com/oxen-io/libsession-util |
| libsession-python (official Python bindings) | https://github.com/oxen-io/libsession-python |
| Session protocol documentation | https://github.com/oxen-io/session-protocol-docs |
| PyNaCl documentation | https://pynacl.readthedocs.io |
| FastAPI documentation | https://fastapi.tiangolo.com |
| Vite documentation | https://vitejs.dev |
| Protobuf Python tutorial | https://protobuf.dev/getting-started/pythontutorial/ |
