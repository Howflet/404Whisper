# Backend Implementation Progress

> Last updated: 2026-04-04 — Initial tracker created.

---

## Summary

| Metric | Value |
|---|---|
| Total entities (DB tables) | 7 |
| Entities complete | 0 / 7 |
| Total endpoints | 23 |
| Endpoints complete | 0 / 23 |
| Unit test coverage | 0% |
| Integration test coverage | 0% |
| Contract test coverage | 0% |

---

## Status Legend

| Symbol | Meaning |
|---|---|
| ⬜ | Not started |
| 🟡 | In progress |
| ✅ | Complete — all tests written and passing |
| ⚠️ | Blocked — see Open Issues |

> A task moves to ✅ only when **all** tests in its row are written **and** passing.
> Update test counts on every run; keep this file as the single source of truth for project status.

---

## Build Order

Development follows the bottom-up layer order defined in `CONTEXT.md`.
No entity in a higher layer may be marked ✅ until all entities it depends on are ✅.

```
Phase 1 (active) → Identity + Cryptography
Phase 2          → Network
Phase 3          → Storage (schema + queries)
Phase 4          → Messaging
Phase 5          → Groups + Attachments
Phase 6          → API / Web Interface
```

---

## Entity Progress

### Identity (`identities` table + `identity/` layer)

| Task | Status | Tests Written | Tests Passing | Notes |
|---|---|---|---|---|
| DB schema — `identities` table | ⬜ | 0 | 0 | |
| `identity/keypair.py` — keypair derivation | ⬜ | 0 | 0 | Must validate against session.js test vectors |
| `identity/mnemonic.py` — encode/decode | ⬜ | 0 | 0 | Session custom word list, not BIP39 |
| `identity/keystore.py` — encrypted storage | ⬜ | 0 | 0 | Argon2 KDF; private key never in DB |
| Pydantic schemas — `IdentityCreateRequest` | ⬜ | 0 | 0 | |
| Pydantic schemas — `IdentityImportRequest` | ⬜ | 0 | 0 | |
| Pydantic schemas — `IdentityResponse` | ⬜ | 0 | 0 | |
| `POST /api/identity/new` | ⬜ | 0 | 0 | Returns mnemonic once only |
| `POST /api/identity/import` | ⬜ | 0 | 0 | |
| `GET /api/identity` | ⬜ | 0 | 0 | |
| `POST /api/identity/unlock` | ⬜ | 0 | 0 | |
| `PATCH /api/identity` | ⬜ | 0 | 0 | personalVibe: aesthetic only |
| Unit tests | ⬜ | 0 | 0 | See `tests/unit/test_validation.py`, `test_business_logic.py` |
| Integration tests | ⬜ | 0 | 0 | See `tests/integration/test_db_identity.py` |
| Contract tests | ⬜ | 0 | 0 | See `tests/contract/test_api_identity.py` |

---

### Contact (`contacts` table)

| Task | Status | Tests Written | Tests Passing | Notes |
|---|---|---|---|---|
| DB schema — `contacts` table | ⬜ | 0 | 0 | |
| `storage/queries.py` — CRUD for contacts | ⬜ | 0 | 0 | |
| Pydantic schemas — `ContactCreateRequest` | ⬜ | 0 | 0 | Session ID validation |
| Pydantic schemas — `ContactResponse` | ⬜ | 0 | 0 | |
| `GET /api/contacts` | ⬜ | 0 | 0 | Filter by `accepted` param |
| `POST /api/contacts` | ⬜ | 0 | 0 | User-initiated → accepted=True |
| `PATCH /api/contacts/{sessionId}` | ⬜ | 0 | 0 | Accept pending request or rename |
| `DELETE /api/contacts/{sessionId}` | ⬜ | 0 | 0 | Hard delete; does not cascade to conversations |
| Integration tests | ⬜ | 0 | 0 | See `tests/integration/test_db_contacts.py` |
| Contract tests | ⬜ | 0 | 0 | See `tests/contract/test_api_contacts.py` |

---

### Conversation (`conversations` table)

| Task | Status | Tests Written | Tests Passing | Notes |
|---|---|---|---|---|
| DB schema — `conversations` table | ⬜ | 0 | 0 | DM/GROUP type constraint + FK check |
| `storage/queries.py` — CRUD + list | ⬜ | 0 | 0 | |
| Pydantic schemas — `ConversationResponse` | ⬜ | 0 | 0 | |
| `GET /api/conversations` | ⬜ | 0 | 0 | Filter by type; order by last_message_at |
| `GET /api/conversations/{id}/messages` | ⬜ | 0 | 0 | Cursor pagination (before + limit) |
| `PATCH /api/conversations/{id}` | ⬜ | 0 | 0 | personalVibeOverride, accepted |
| Integration tests | ⬜ | 0 | 0 | |
| Contract tests | ⬜ | 0 | 0 | See `tests/contract/test_api_messages.py` |

---

### Message (`messages` table)

| Task | Status | Tests Written | Tests Passing | Notes |
|---|---|---|---|---|
| DB schema — `messages` table | ⬜ | 0 | 0 | All vibe-specific columns (expires_at, deliver_after, is_anonymous, etc.) |
| `storage/queries.py` — create + paginated list | ⬜ | 0 | 0 | |
| `messaging/compose.py` — protobuf encoding | ⬜ | 0 | 0 | Requires Phase 2 (network) to send |
| `messaging/parse.py` — protobuf decoding | ⬜ | 0 | 0 | |
| `messaging/ttl.py` — 404 vibe expiry logic | ⬜ | 0 | 0 | Forward-only; countdown continues on exit; purge skips is_pinned=1 |
| `messaging/delay.py` — SLOW_BURN delay logic | ⬜ | 0 | 0 | Fixed 60 s constant (`SLOW_BURN_DELAY_SECONDS = 60`) |
| Pydantic schemas — `MessageSendRequest` | ⬜ | 0 | 0 | body OR attachmentId required; body max 2000 chars |
| Pydantic schemas — `MessageResponse` | ⬜ | 0 | 0 | Includes isPinned, chorusGroupId; CONFESSIONAL: senderSessionId=null |
| `POST /api/messages/send` | ⬜ | 0 | 0 | |
| `POST /api/messages/{id}/pin` | ⬜ | 0 | 0 | Any member; 404 escape hatch |
| `DELETE /api/messages/{id}/pin` | ⬜ | 0 | 0 | Countdown resumes if expiresAt still in future |
| Integration tests | ⬜ | 0 | 0 | See `tests/integration/test_db_messages.py` |
| Contract tests | ⬜ | 0 | 0 | See `tests/contract/test_api_messages.py` |

---

### Group (`groups` + `group_members` tables)

| Task | Status | Tests Written | Tests Passing | Notes |
|---|---|---|---|---|
| DB schema — `groups` table | ⬜ | 0 | 0 | Vibe cooldown columns |
| DB schema — `group_members` table | ⬜ | 0 | 0 | Cascade delete on group delete |
| `storage/queries.py` — group CRUD | ⬜ | 0 | 0 | |
| `groups/create.py` — group creation | ⬜ | 0 | 0 | Key distribution via Session protocol |
| `groups/members.py` — add/remove/leave | ⬜ | 0 | 0 | Admin permission enforcement |
| `api/services/vibes.py` — vibe classification | ⬜ | 0 | 0 | is_behavioral, requires_admin, cooldown |
| Pydantic schemas — `GroupCreateRequest` | ⬜ | 0 | 0 | |
| Pydantic schemas — `GroupResponse` | ⬜ | 0 | 0 | |
| `POST /api/groups` | ⬜ | 0 | 0 | |
| `GET /api/groups/{id}` | ⬜ | 0 | 0 | Includes members array |
| `PATCH /api/groups/{id}` | ⬜ | 0 | 0 | Cooldown enforcement; admin check for behavioral vibes |
| `POST /api/groups/{id}/members` | ⬜ | 0 | 0 | Admin only |
| `DELETE /api/groups/{id}/members/{sessionId}` | ⬜ | 0 | 0 | Admin only |
| `POST /api/groups/{id}/leave` | ⬜ | 0 | 0 | Broadcasts MEMBER_LEFT system message |
| Integration tests | ⬜ | 0 | 0 | See `tests/integration/test_db_groups.py` |
| Contract tests | ⬜ | 0 | 0 | See `tests/contract/test_api_groups.py` |

---

### Attachment (`attachments` table)

| Task | Status | Tests Written | Tests Passing | Notes |
|---|---|---|---|---|
| DB schema — `attachments` table | ⬜ | 0 | 0 | encryption_key + hmac_key as BLOB; never exposed via API |
| `attachments/upload.py` — encrypt + upload | ⬜ | 0 | 0 | AES-256-CBC + HMAC-SHA256; `MAX_ATTACHMENT_BYTES = 10_485_760` |
| `attachments/download.py` — download + decrypt | ⬜ | 0 | 0 | |
| Pydantic schemas — `AttachmentResponse` | ⬜ | 0 | 0 | encryptionKey must NEVER appear |
| `POST /api/attachments/upload` | ⬜ | 0 | 0 | multipart/form-data |
| `GET /api/attachments/{id}` | ⬜ | 0 | 0 | Returns raw binary; Content-Disposition header |
| Integration tests | ⬜ | 0 | 0 | See `tests/integration/test_db_attachments.py` |
| Contract tests | ⬜ | 0 | 0 | See `tests/contract/test_api_attachments.py` |

---

### WebSocket + Real-time Layer (`api/ws.py`)

| Task | Status | Tests Written | Tests Passing | Notes |
|---|---|---|---|---|
| WS endpoint — connection handling | ⬜ | 0 | 0 | |
| Event: `message_received` | ⬜ | 0 | 0 | |
| Event: `attachment_progress` | ⬜ | 0 | 0 | |
| Event: `vibe_changed` | ⬜ | 0 | 0 | |
| Event: `conversation_request` | ⬜ | 0 | 0 | |
| Event: `identity_locked` | ⬜ | 0 | 0 | Fires after 15 min inactivity; polling loop does NOT reset timer |
| Contract tests | ⬜ | 0 | 0 | See `tests/contract/test_api_websocket.py` |

---

### Cross-Layer Consistency

| Task | Status | Tests Written | Tests Passing | Notes |
|---|---|---|---|---|
| VibeId enum — API ↔ DB sync | ⬜ | 0 | 0 | See `tests/consistency/test_cross_layer.py` |
| AttachmentStatus enum — API ↔ DB sync | ⬜ | 0 | 0 | |
| MessageType enum — API ↔ DB sync | ⬜ | 0 | 0 | |
| API response fields — camelCase compliance | ⬜ | 0 | 0 | |
| DB column names — snake_case compliance | ⬜ | 0 | 0 | |

---

## Open Issues & Blockers

*All open questions from v0.1.0 are now resolved. No active blockers.*

| # | Issue | Related Entity | Status | Decision |
|---|---|---|---|---|
| OQ-1 | Vibe cooldown duration | Conversation, Group | ✅ Closed | **5 minutes** |
| OQ-2 | 404 vibe — retroactive vs. forward-only | Message | ✅ Closed | **Forward-only** |
| OQ-3 | 404 vibe — switching out behaviour | Message | ✅ Closed | **Countdown continues to expiry** |
| OQ-4 | 404 vibe — pin escape hatch | Message | ✅ Closed | **Yes — `is_pinned` + pin/unpin endpoints** |
| OQ-5 | Chorus grouping window | Message | ✅ Closed | **30-second window; `chorus_group_id` UUID in DB** |
| OQ-6 | Slow Burn delay | Message | ✅ Closed | **Fixed 60 s constant** |
| OQ-7 | Session file size limit | Attachment | ✅ Closed | **10 MiB (`MAX_ATTACHMENT_BYTES = 10_485_760`)** |
| OQ-8 | Default API port | API | ✅ Closed | **8000 (FastAPI); 5173 (Vite); env-var overridable** |
| OQ-9 | Message body max length | Message | ✅ Closed | **2,000 characters** (confirmed) |
| OQ-10 | Keystore idle lock timeout | Identity, WebSocket | ✅ Closed | **15 minutes; polling loop does not reset timer** |
| OQ-11 | SCRAMBLE vibe interval | Conversation | ✅ Closed | **Client-side only; random 30–120 s; no server event** |
| OQ-12 | CHORUS admin requirement | Group | ✅ Closed | **Admin-only (behavioral classification confirmed)** |

---

## Change Log

| Date | What Changed | Reason |
|---|---|---|
| 2026-04-04 | Initial `PROGRESS.md` created | Project kickoff |
| 2026-04-04 | Test suite scaffolded (`tests/unit/`, `tests/integration/`, `tests/contract/`, `tests/consistency/`) | TDD workflow established |
| 2026-04-04 | `DATA_CONTRACT.md` v0.1.0 created | Data contract derived from `CONTEXT.md` |
| 2026-04-04 | `DATA_CONTRACT.md` promoted to v0.2.0 — all 12 open questions resolved | Unblocks full backend implementation |
| 2026-04-04 | `messages` schema: added `is_pinned`, `chorus_group_id` columns | OQ-4 and OQ-5 decisions; pin endpoints added |
| 2026-04-04 | All OQ blockers cleared from task rows | Decisions finalised |
