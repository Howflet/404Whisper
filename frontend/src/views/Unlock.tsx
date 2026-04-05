import React, { useState } from 'react';
import { api, ApiError } from '../api/client';

interface UnlockProps {
  onUnlocked: () => void;
}

function Unlock({ onUnlocked }: UnlockProps) {
  const [passphrase, setPassphrase] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await api.unlockIdentity(passphrase);
      onUnlocked();
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

  return (
    <div className="unlock">
      <h1>Unlock Identity</h1>
      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="passphrase">Passphrase:</label>
          <input
            type="password"
            id="passphrase"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            placeholder="Enter your passphrase"
            required
          />
        </div>

        {error && <div className="error">{error}</div>}

        <button type="submit" disabled={loading}>
          {loading ? 'Unlocking...' : 'Unlock'}
        </button>
      </form>
    </div>
  );
}

export default Unlock;