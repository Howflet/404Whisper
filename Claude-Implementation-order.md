# 404Whisper: Implementation Order Plan

## Context

404Whisper is a decentralized, end-to-end encrypted messaging app built on the Session protocol.
The frontend (React/TS), data contracts, test suite, and DB schema are all largely in place.
The backend protocol stack (crypto, network, messaging) is entirely empty.
This plan sequences implementation from the bottom of the 8-layer stack upward,
because each layer is a strict prerequisite for the one above it.

---

## Dependency Graph (Why This Order)

```
Layer 1 (Identity)  ← already ~60%, just mnemonic stub to fix
      ↓
Layer 2 (Crypto)    ← X25519 DH + Ed25519 + XSalsa20 + onion packets
      ↓
Layer 7 (Storage)   ← DB CRUD gaps must be filled before networking writes to it
      ↓
Layer 3 (Network)   ← service node discovery + swarm lookup + onion dispatch
      ↓
Layer 4 (Messaging) ← protobuf encode/decode + send + polling receive loop
      ↓
Layer 5 (Groups)    ← group key distribution relies on messaging + crypto
      ↓
Layer 6 (Attachments) ← encrypt + upload to file server + download decrypt
      ↓
Layer 8 (API/WS)    ← wire real data into all 501 routes + WebSocket events
```

---

## Feature Order

### 1. Complete Layer 1 — `identity/mnemonic.py`
**Why first:** Every other layer uses Session IDs. The mnemonic encode/decode is the last
identity gap and blocks import-from-seed-phrase user flow. Keystore + keypair are already done.

**What to build:**
- Real Session word list (2048-word BIP39-compatible list used by Session protocol)
- `encode(seed_bytes) → str` — convert 32-byte seed to 13-word mnemonic
- `decode(mnemonic_str) → bytes` — reverse; validate checksum word
- Replace hardcoded mock in `mnemonic.py`
- Make `identity/__init__.py` wire `create_identity()` and `import_from_mnemonic()` end-to-end

**Files:** `404whisper/identity/mnemonic.py`, `404whisper/identity/__init__.py`
**Tests to pass:** `tests/unit/test_business_logic.py` mnemonic tests

---

### 2. Complete Layer 2 — `crypto/`
**Why second:** Sending or receiving any Session message requires X25519 DH for shared secrets,
Ed25519 for signing envelopes, and XSalsa20-Poly1305 for message encryption.
Onion routing also requires layered encryption.

**What to build:**
- `crypto/x25519.py` — DH key exchange (X25519) using PyNaCl
- `crypto/ed25519.py` — sign + verify using Ed25519 (PyNaCl)
- `crypto/symmetric.py` — XSalsa20-Poly1305 encrypt/decrypt (NaCl box)
- `crypto/onion.py` — build 3-layer onion packet (encrypt payload for each hop)
- `crypto/__init__.py` — public surface: `encrypt_message()`, `decrypt_message()`, `sign()`, `verify()`

**Files:** `404whisper/crypto/` (currently `.gitkeep` only)
**Tests to pass:** `tests/unit/` crypto-related assertions

---

### 3. Fill Storage Gaps — `storage/database.py`
**Why third:** Network and messaging layers will write received messages, contacts, and
conversation state to the DB. CRUD must be complete before those writes happen.

**What to build:**
- Verify all 7 tables have full insert/select/update/delete implementations
- Confirm `upsert_contact()`, `save_message()`, `update_conversation_unread()` exist
- Add missing methods surfaced by `tests/integration/` failures

**Files:** `404whisper/storage/database.py`
**Tests to pass:** All `tests/integration/test_db_*.py`

---

### 4. Build Layer 3 — `network/`
**Why fourth:** Without network, messages can't be sent or received. This layer discovers
service nodes, resolves which swarm holds a recipient's messages, and dispatches onion requests.

**What to build:**
- `network/nodes.py` — fetch seed node list; request service node list from the network
- `network/swarm.py` — query swarm for a given Session ID's messages
- `network/onion_request.py` — wrap a request in onion layers + send via HTTP to guard node
- `network/__init__.py` — public surface: `send_onion_request()`, `get_swarm_nodes()`

**Files:** `404whisper/network/` (currently `.gitkeep` only)

---

### 5. Build Layer 4 — `messaging/`
**Why fifth:** Core send/receive loop. Depends on crypto (to encrypt/decrypt) and network
(to dispatch). This is the heart of the app.

**What to build:**
- `messaging/proto/` — protobuf definitions for Session envelope + content message
- `messaging/compose.py` — build + sign + encrypt outgoing message envelope
- `messaging/parse.py` — decrypt + verify + deserialize incoming envelope
- `messaging/send.py` — store in DB, serialize, dispatch via `network.send_onion_request()`
- `messaging/poll.py` — background async polling loop; call swarm, decrypt each message, write to DB, emit WebSocket event
- `messaging/__init__.py` — `send_message()`, `start_polling()`

**Files:** `404whisper/messaging/` (currently `.gitkeep` only)
**Tests to pass:** `tests/contract/test_api_messages.py`, `tests/contract/test_api_websocket.py`

Complete the API routes:
- `POST /api/messages/send` — call `messaging.send_message()`
- `GET /api/conversations/{id}/messages` — DB read with pagination
- WebSocket: emit `message_received` from polling loop

**Files:** `404whisper/api/routes/conversations.py`

---

### 6. Build Layer 5 — `groups/`
**Why sixth:** Groups require working 1-to-1 messaging (key distribution uses individual
encrypted messages to each member). Admin flows (add/remove member) also depend on messaging.

**What to build:**
- `groups/keys.py` — generate group encryption key; encrypt for each member; distribute
- `groups/membership.py` — add/remove member logic; update `group_members` table
- `groups/__init__.py` — `create_group()`, `add_member()`, `remove_member()`, `leave_group()`

**Files:** `404whisper/groups/` (currently `.gitkeep` only)
**Tests to pass:** `tests/contract/test_api_groups.py`, `tests/integration/test_db_groups.py`

Complete the API routes (currently 501):
- `GET /api/groups/{id}`
- `PATCH /api/groups/{id}`
- `POST /api/groups/{id}/members`
- `DELETE /api/groups/{id}/members/{sessionId}`
- `POST /api/groups/{id}/leave`

**Files:** `404whisper/api/routes/groups.py`

---

### 7. Build Layer 6 — `attachments/`
**Why seventh:** Attachments need a working message layer to reference the uploaded file's
metadata in the message body.

**What to build:**
- `attachments/encrypt.py` — AES-256-CBC + HMAC-SHA256 encrypt file bytes; generate keys
- `attachments/upload.py` — POST encrypted bytes to Session file server; return `upload_url`
- `attachments/download.py` — fetch URL, decrypt with stored keys, verify HMAC
- `attachments/__init__.py` — `upload_attachment()`, `download_attachment()`

**Files:** `404whisper/attachments/` (currently `.gitkeep` only)
**Tests to pass:** `tests/contract/test_api_attachments.py`, `tests/integration/test_db_attachments.py`

Complete API routes:
- `POST /api/attachments/upload`
- `GET /api/attachments/{id}`
- WebSocket: emit `attachment_progress` events during upload/download

---

### 8. Wire Layer 8 — Remaining API Routes + Contact Endpoints
**Why last:** All the domain logic is now in place; this is purely connecting routes to it.

**What to build:**
- `POST /api/contacts` — add contact to DB
- `GET /api/contacts` — list contacts
- `PATCH /api/contacts/{sessionId}` — update contact name/accepted
- `DELETE /api/contacts/{sessionId}` — remove contact
- `PATCH /api/conversations/{id}` — update vibe/override + emit `vibe_changed` WS event
- `POST /api/messages/{id}/pin` / `DELETE /api/messages/{id}/pin`
- `POST /api/conversations` — create 1-to-1 conversation
- Lock/unlock lifecycle (`POST /api/identity/lock`, idle timeout → `identity_locked` WS event)
- Contacts API is currently entirely missing; add `api/routes/contacts.py` and register it

**Files:** `404whisper/api/routes/contacts.py` (new), `404whisper/api/routes/conversations.py`, `404whisper/main.py`
**Tests to pass:** `tests/contract/test_api_contacts.py`, `tests/consistency/test_cross_layer.py`

---

## Verification Plan

After each layer, run the relevant test scope:

| Layer | Command |
|-------|---------|
| 1 (mnemonic) | `pytest tests/unit/test_business_logic.py -k mnemonic` |
| 2 (crypto) | `pytest tests/unit/ -k crypto` |
| 3 (storage) | `pytest -m integration` |
| 4 (network) | manual `curl` to seed node, check node list returned |
| 5 (messaging) | `pytest tests/contract/test_api_messages.py tests/contract/test_api_websocket.py` |
| 6 (groups) | `pytest tests/contract/test_api_groups.py tests/integration/test_db_groups.py` |
| 7 (attachments) | `pytest tests/contract/test_api_attachments.py` |
| 8 (API wiring) | `pytest tests/contract/ tests/consistency/` |
| Full | `pytest && cd frontend && npm test` |
