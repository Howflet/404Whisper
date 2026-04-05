"""
Conversations API Routes

Handles conversation listing and management.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import sys
sys.path.append(os.path.dirname(__file__) + '/../..')
from storage.database import Database

router = APIRouter()

# Mock data - TODO: Integrate with database
mock_conversations = []

class ConversationResponse(BaseModel):
    id: int
    type: str  # "DM" or "GROUP"
    contact: Optional[dict] = None
    group: Optional[dict] = None
    lastMessage: Optional[dict] = None
    unreadCount: int
    groupVibe: Optional[str] = None
    personalVibeOverride: Optional[str] = None
    vibeCooldownUntil: Optional[str] = None
    accepted: bool
    createdAt: str
    updatedAt: str

# For now, use a test passphrase - in production, get from unlocked identity
TEST_PASSPHRASE = "test123"
DB_PATH = os.path.join(os.path.dirname(__file__), '../../data/conversations.db')

def get_database():
    return Database(DB_PATH, TEST_PASSPHRASE)

@router.get("/conversations")
async def get_conversations(type_filter: Optional[str] = None) -> dict:
    """Get all conversations"""
    try:
        db = get_database()
        raw_conversations = db.get_conversations()
        
        conversations = []
        for conv in raw_conversations:
            # Transform to expected format
            conv_dict = {
                "id": conv["id"],
                "type": "GROUP" if conv["group_id"] else "DM",
                "contact": None if conv["group_id"] else {"sessionId": conv["contact_session_id"], "displayName": None},
                "group": {"id": conv["group_id"], "name": f"Group {conv['group_id']}", "memberCount": 0} if conv["group_id"] else None,
                "lastMessage": None,  # TODO: Get from messages
                "unreadCount": 0,
                "groupVibe": None,
                "personalVibeOverride": None,
                "vibeCooldownUntil": None,
                "accepted": True,
                "createdAt": conv["created_at"],
                "updatedAt": conv["last_message_at"] or conv["created_at"]
            }
            conversations.append(conv_dict)
        
        if type_filter:
            conversations = [c for c in conversations if c["type"] == type_filter]
        
        return {"conversations": conversations}
    except Exception as e:
        # Fallback to mock data
        return {"conversations": []}

@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int) -> ConversationResponse:
    """Get conversation details"""
    # TODO: Implement
    return JSONResponse(status_code=501, content={"error": {"code": "NOT_IMPLEMENTED", "message": "Not implemented"}})

@router.post("/conversations")
async def create_conversation():
    """Create a new conversation"""
    # TODO: Implement
    return JSONResponse(status_code=501, content={"error": {"code": "NOT_IMPLEMENTED", "message": "Not implemented"}})

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int):
    """Delete a conversation"""
    # TODO: Implement
    return JSONResponse(status_code=501, content={"error": {"code": "NOT_IMPLEMENTED", "message": "Not implemented"}})