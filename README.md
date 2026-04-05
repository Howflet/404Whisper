# 404Whisper

A messaging app like WhatsApp or Telegram, but works without phone number or email, using Session protocol for secure, decentralized messaging.

## What We've Done

### Backend (FastAPI)
- WebSocket support for real-time updates
- Identity management (create/import identities)
- Group creation with auto-linked conversations
- Conversation listing
- Encrypted SQLite database with lazy initialization
- API routes for identity, groups, conversations

### Frontend (React + Vite)
- WebSocket client for real-time updates
- API client for REST endpoints
- Basic UI for conversations list
- Proxy configuration for API calls to backend

### Infrastructure
- Python virtual environment
- Node.js dependencies
- Testing with pytest (11/11 tests passing)

## What Still Needs to Be Done

### Core Features
- Message sending/receiving
- Attachment handling (files, images)
- Group management (add/remove members)
- User contacts/friends
- Message encryption/decryption

### UI/UX
- Message view and input
- Group creation UI
- User profile management
- Better error handling and loading states

### Backend
- Message storage and retrieval
- Attachment processing
- User authentication/session management
- Network layer for peer-to-peer messaging

### Testing
- Integration tests for messaging flow
- End-to-end tests
- UI tests

### Deployment
- Production build configuration
- Docker setup
- Session protocol integration

## How to Run

### Backend
```bash
cd 404whisper
python main.py
```

### Frontend
```bash
cd frontend
npm run dev
```

### Tests
```bash
pytest
```

## Architecture

See CONTEXT.md, DATA_CONTRACT.md, PROGRESS.md for detailed documentation.