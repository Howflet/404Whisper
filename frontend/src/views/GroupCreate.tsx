import React, { useState } from 'react';
import { api, ApiError } from '../api/client';

interface GroupCreateProps {
  onClose: () => void;
  onCreated: () => void;
}

function GroupCreate({ onClose, onCreated }: GroupCreateProps) {
  const [groupName, setGroupName] = useState('');
  const [memberIds, setMemberIds] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // Parse member IDs from comma or newline separated input
      const ids = memberIds
        .split(/[,\n]/)
        .map((id) => id.trim())
        .filter((id) => id.length > 0);

      // Validate all Session IDs
      const sessionIdRegex = /^05[0-9a-f]{64}$/i;
      for (const id of ids) {
        if (!sessionIdRegex.test(id)) {
          setError(`Invalid Session ID: ${id}`);
          setLoading(false);
          return;
        }
      }

      if (!groupName.trim()) {
        setError('Group name is required');
        setLoading(false);
        return;
      }

      await api.createGroup(groupName, ids.length > 0 ? ids : undefined);
      onCreated();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to create group');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-header">
          <h2>Create New Group</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSubmit} className="modal-content">
          <div className="form-group">
            <label htmlFor="groupName">Group Name *</label>
            <input
              type="text"
              id="groupName"
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              placeholder="e.g., Night Owls"
              maxLength={64}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="memberIds">Members (optional)</label>
            <textarea
              id="memberIds"
              value={memberIds}
              onChange={(e) => setMemberIds(e.target.value)}
              placeholder="Enter Session IDs, one per line or comma-separated&#10;057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5c"
            />
            <p className="help-text">Leave empty to create an empty group. You can add members later.</p>
          </div>

          {error && <div className="error">{error}</div>}

          <div className="modal-actions">
            <button type="button" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" disabled={loading || !groupName.trim()}>
              {loading ? 'Creating...' : 'Create Group'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default GroupCreate;