import React, { useState, useEffect } from 'react';
import { api, ApiError } from '../api/client';

interface GroupMember {
  sessionId: string;
  displayName: string | null;
  isAdmin: boolean;
  joinedAt: string;
}

interface GroupMembersProps {
  groupId: number;
  isAdmin: boolean;
  onClose: () => void;
}

function GroupMembers({ groupId, isAdmin, onClose }: GroupMembersProps) {
  const [members, setMembers] = useState<GroupMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addingMembers, setAddingMembers] = useState(false);
  const [newMemberIds, setNewMemberIds] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);

  useEffect(() => {
    loadMembers();
  }, [groupId]);

  const loadMembers = async () => {
    setLoading(true);
    try {
      const group = await api.getGroup(groupId);
      setMembers(group.members);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to load members');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleAddMembers = async (e: React.FormEvent) => {
    e.preventDefault();
    setAddingMembers(true);
    setError(null);

    try {
      const ids = newMemberIds
        .split(/[,\n]/)
        .map((id) => id.trim())
        .filter((id) => id.length > 0);

      if (ids.length === 0) {
        setError('Please enter at least one Session ID');
        setAddingMembers(false);
        return;
      }

      const sessionIdRegex = /^05[0-9a-f]{64}$/i;
      for (const id of ids) {
        if (!sessionIdRegex.test(id)) {
          setError(`Invalid Session ID: ${id}`);
          setAddingMembers(false);
          return;
        }
      }

      await api.addGroupMembers(groupId, ids);
      await loadMembers();
      setNewMemberIds('');
      setShowAddForm(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to add members');
      }
    } finally {
      setAddingMembers(false);
    }
  };

  const handleRemoveMember = async (sessionId: string) => {
    if (!confirm('Remove this member?')) return;

    try {
      await api.removeGroupMember(groupId, sessionId);
      await loadMembers();
    } catch (err) {
      setError('Failed to remove member');
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Group Members</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="modal-content">
          {loading ? (
            <p>Loading members...</p>
          ) : (
            <>
              <div className="members-list">
                {members.map((member) => (
                  <div key={member.sessionId} className="member-item">
                    <div className="member-info">
                      <div className="member-name">
                        {member.displayName || member.sessionId.slice(0, 15)}...
                        {member.isAdmin && <span className="admin-badge">Admin</span>}
                      </div>
                      <div className="member-id">{member.sessionId}</div>
                    </div>
                    {isAdmin && (
                      <button
                        className="remove-member-btn"
                        onClick={() => handleRemoveMember(member.sessionId)}
                        title="Remove member"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))}
              </div>

              {isAdmin && (
                <>
                  {!showAddForm ? (
                    <button
                      onClick={() => setShowAddForm(true)}
                      className="add-members-btn"
                    >
                      Add Members
                    </button>
                  ) : (
                    <form onSubmit={handleAddMembers} className="add-members-form">
                      <textarea
                        value={newMemberIds}
                        onChange={(e) => setNewMemberIds(e.target.value)}
                        placeholder="Enter Session IDs, one per line or comma-separated"
                        disabled={addingMembers}
                      />
                      <div className="form-actions">
                        <button
                          type="button"
                          onClick={() => {
                            setShowAddForm(false);
                            setNewMemberIds('');
                          }}
                          disabled={addingMembers}
                        >
                          Cancel
                        </button>
                        <button type="submit" disabled={addingMembers || !newMemberIds.trim()}>
                          {addingMembers ? 'Adding...' : 'Add'}
                        </button>
                      </div>
                    </form>
                  )}
                </>
              )}

              {error && <div className="error">{error}</div>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default GroupMembers;