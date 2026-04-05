import React, { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Identity } from '../types';

interface SetupProps {
  onIdentityCreated: (identity: Identity) => void;
}

function Setup({ onIdentityCreated }: SetupProps) {
  const [mode, setMode] = useState<'new' | 'import'>('new');
  const [passphrase, setPassphrase] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [mnemonic, setMnemonic] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdIdentity, setCreatedIdentity] = useState<{ sessionId: string; mnemonic: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      let result;
      if (mode === 'new') {
        result = await api.createIdentity(passphrase, displayName || undefined);
        setCreatedIdentity({ sessionId: result.sessionId, mnemonic: result.mnemonic });
      } else {
        result = await api.importIdentity(mnemonic, passphrase, displayName || undefined);
      }
      onIdentityCreated({
        sessionId: result.sessionId,
        displayName: result.displayName,
        personalVibe: null,
        createdAt: result.createdAt,
      });
    } catch (error) {
      if (error instanceof ApiError) {
        setError(error.message);
      } else {
        setError('An unexpected error occurred');
      }
    } finally {
      setLoading(false);
    }
  };

  if (createdIdentity) {
    return (
      <div className="setup success">
        <h1>Identity Created!</h1>
        <p><strong>Session ID:</strong> {createdIdentity.sessionId}</p>
        <p><strong>Mnemonic (save this securely):</strong></p>
        <pre>{createdIdentity.mnemonic}</pre>
        <p>This mnemonic is shown only once. Store it safely!</p>
        <button onClick={() => setCreatedIdentity(null)}>Continue</button>
      </div>
    );
  }

  return (
    <div className="setup">
      <h1>404Whisper Setup</h1>
      <div className="mode-selector">
        <button onClick={() => setMode('new')} className={mode === 'new' ? 'active' : ''}>
          Create New Identity
        </button>
        <button onClick={() => setMode('import')} className={mode === 'import' ? 'active' : ''}>
          Import Existing Identity
        </button>
      </div>

      <form onSubmit={handleSubmit}>
        {mode === 'import' && (
          <div>
            <label htmlFor="mnemonic">Mnemonic Seed Phrase:</label>
            <textarea
              id="mnemonic"
              value={mnemonic}
              onChange={(e) => setMnemonic(e.target.value)}
              placeholder="Enter your 12-24 word seed phrase"
              required
            />
          </div>
        )}

        <div>
          <label htmlFor="passphrase">Passphrase:</label>
          <input
            type="password"
            id="passphrase"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            placeholder="Choose a strong passphrase"
            minLength={8}
            required
          />
        </div>

        <div>
          <label htmlFor="displayName">Display Name (optional):</label>
          <input
            type="text"
            id="displayName"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Your display name"
            maxLength={64}
          />
        </div>

        {error && <div className="error">{error}</div>}

        <button type="submit" disabled={loading}>
          {loading ? 'Creating...' : mode === 'new' ? 'Create Identity' : 'Import Identity'}
        </button>
      </form>
    </div>
  );
}

export default Setup;