import React, { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { VibeId } from '../types';

const AESTHETIC_VIBES: VibeId[] = ['CAMPFIRE', 'NEON', 'LIBRARY', 'VOID', 'SUNRISE'];

interface SettingsPanelProps {
  sessionId: string;
  displayName: string | null;
  personalVibe: VibeId | null;
  onClose: () => void;
  onUpdate: () => void;
}

function SettingsPanel({ sessionId, displayName, personalVibe, onClose, onUpdate }: SettingsPanelProps) {
  const [newDisplayName, setNewDisplayName] = useState(displayName || '');
  const [newVibe, setNewVibe] = useState<VibeId | null>(personalVibe);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCopySessionId = () => {
    navigator.clipboard.writeText(sessionId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await api.updateIdentity({
        displayName: newDisplayName || null,
        personalVibe: newVibe,
      });
      onUpdate();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to update settings');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="settings-overlay">
      <div className="settings-panel">
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="settings-content">
          <div className="session-id-section">
            <h3>Your Session ID</h3>
            <div className="session-id-display">
              <code>{sessionId}</code>
              <button 
                className="copy-btn"
                onClick={handleCopySessionId}
                title="Copy Session ID"
              >
                {copied ? '✓ Copied' : 'Copy'}
              </button>
            </div>
            <p className="help-text">Share this ID with others to start a conversation. They'll need to add you manually.</p>
          </div>

          <form onSubmit={handleSave}>
            <div className="form-group">
              <label htmlFor="displayName">Display Name</label>
              <input
                type="text"
                id="displayName"
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
                maxLength={64}
              />
            </div>

            <div className="form-group">
              <label htmlFor="personalVibe">My Vibe (aesthetic only)</label>
              <select
                id="personalVibe"
                value={newVibe || ''}
                onChange={(e) => setNewVibe((e.target.value as VibeId) || null)}
              >
                <option value="">None</option>
                {AESTHETIC_VIBES.map((vibe) => (
                  <option key={vibe} value={vibe}>
                    {vibe}
                  </option>
                ))}
              </select>
              <p className="help-text">Aesthetic vibes affect only your view. Behavioral vibes require group settings.</p>
            </div>

            {error && <div className="error">{error}</div>}

            <div className="form-actions">
              <button type="button" onClick={onClose} disabled={loading}>
                Cancel
              </button>
              <button type="submit" disabled={loading}>
                {loading ? 'Saving...' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default SettingsPanel;