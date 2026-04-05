"""
Groups API Routes

Handles group creation, management, and membership.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import sys
sys.path.append(os.path.dirname(__file__) + '/../..')
from storage.database import Database
from datetime import datetime

router = APIRouter()

# Database setup
TEST_PASSPHRASE = "test123"
DB_PATH = os.path.join(os.path.dirname(__file__), '../../data/test.db')

def get_database():
    return Database(DB_PATH, TEST_PASSPHRASE)

# Data models
class GroupMember(BaseModel):
    sessionId: str
    displayName: Optional[str] = None
    joinedAt: str

class GroupResponse(BaseModel):
    id: int
    groupSessionId: str
    name: str
    memberCount: int
    vibe: Optional[str] = None
    vibeCooldownUntil: Optional[str] = None
    createdAt: str

class CreateGroupRequest(BaseModel):
    name: str
    memberSessionIds: Optional[List[str]] = None

@router.post("/groups")
async def create_group(request: CreateGroupRequest) -> dict:
    """Create a new group and auto-create a conversation for it"""
    try:
        db = get_database()
        
        # Create group in database
        group_id = db.create_group(
            name=request.name,
            group_vibe=None
        )
        
        # Auto-create a conversation linked to this group
        conversation_id = db.create_conversation(
            contact_session_id=None,
            group_id=group_id
        )
        
        # Return the conversation so frontend knows what to display
        return {
            "id": conversation_id,
            "type": "GROUP",
            "group": {
                "id": group_id,
                "name": request.name,
                "memberCount": len(request.memberSessionIds) if request.memberSessionIds else 0
            },
            "lastMessage": None,
            "unreadCount": 0,
            "groupVibe": None,
            "personalVibeOverride": None,
            "vibeCooldownUntil": None,
            "accepted": True,
            "createdAt": datetime.now().isoformat(),
            "updatedAt": datetime.now().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": str(e)}}
        )

@router.get("/groups/{group_id}")
async def get_group(group_id: int) -> GroupResponse:
    """Get group details"""
    if group_id not in mock_groups:
        return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": "Group not found"}})
    return mock_groups[group_id]

@router.patch("/groups/{group_id}")
async def update_group(group_id: int):
    """Update group settings"""
    # TODO: Implement
    return JSONResponse(status_code=501, content={"error": {"code": "NOT_IMPLEMENTED", "message": "Not implemented"}})

@router.post("/groups/{group_id}/members")
async def add_group_members(group_id: int):
    """Add members to group"""
    # TODO: Implement
    return JSONResponse(status_code=501, content={"error": {"code": "NOT_IMPLEMENTED", "message": "Not implemented"}})

@router.delete("/groups/{group_id}/members/{session_id}")
async def remove_group_member(group_id: int, session_id: str):
    """Remove member from group"""
    # TODO: Implement
    return JSONResponse(status_code=501, content={"error": {"code": "NOT_IMPLEMENTED", "message": "Not implemented"}})

@router.post("/groups/{group_id}/leave")
async def leave_group(group_id: int):
    """Leave group"""
    # TODO: Implement
    return {"ok": True}