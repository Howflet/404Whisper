import React from 'react';
import type { AttachmentStatus } from '../types';

interface AttachmentProgressProps {
  fileName: string;
  status: AttachmentStatus;
  progressPercent: number;
  error?: string | null;
}

function AttachmentProgress({ fileName, status, progressPercent, error }: AttachmentProgressProps) {
  const getStatusLabel = (status: AttachmentStatus) => {
    switch (status) {
      case 'PENDING':
        return 'Pending';
      case 'UPLOADING':
        return 'Uploading';
      case 'UPLOADED':
        return 'Uploaded';
      case 'DOWNLOADING':
        return 'Downloading';
      case 'DOWNLOADED':
        return 'Downloaded';
      case 'FAILED':
        return 'Failed';
      default:
        return status;
    }
  };

  const isActive = status === 'UPLOADING' || status === 'DOWNLOADING';

  return (
    <div className={`attachment-progress ${status}`}>
      <div className="attachment-header">
        <div className="attachment-name">{fileName}</div>
        <div className="attachment-status">{getStatusLabel(status)}</div>
      </div>
      {isActive && (
        <div className="progress-bar-container">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="progress-percent">{progressPercent}%</div>
        </div>
      )}
      {error && <div className="attachment-error">{error}</div>}
    </div>
  );
}

export default AttachmentProgress;