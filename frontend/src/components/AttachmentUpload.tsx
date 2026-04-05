import React, { useRef } from 'react';

interface AttachmentUploadProps {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

function AttachmentUpload({ onFileSelected, disabled = false }: AttachmentUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onFileSelected(file);
      // Reset input so the same file can be selected again
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        onChange={handleFileChange}
        style={{ display: 'none' }}
        disabled={disabled}
      />
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        className="attachment-upload-btn"
        disabled={disabled}
        title="Attach file"
      >
        📎
      </button>
    </>
  );
}

export default AttachmentUpload;