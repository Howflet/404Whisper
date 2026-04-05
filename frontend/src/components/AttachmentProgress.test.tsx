import { render, screen } from '@testing-library/react';
import AttachmentProgress from '../components/AttachmentProgress';

describe('AttachmentProgress', () => {
  it('renders attachment name and status', () => {
    render(
      <AttachmentProgress
        fileName="document.pdf"
        status="UPLOADED"
        progressPercent={100}
      />
    );

    expect(screen.getByText('document.pdf')).toBeInTheDocument();
    expect(screen.getByText('Uploaded')).toBeInTheDocument();
  });

  it('shows progress bar for uploading status', () => {
    render(
      <AttachmentProgress
        fileName="large-file.zip"
        status="UPLOADING"
        progressPercent={45}
      />
    );

    expect(screen.getByText('Uploading')).toBeInTheDocument();
    expect(screen.getByText('45%')).toBeInTheDocument();
  });

  it('displays error message when provided', () => {
    render(
      <AttachmentProgress
        fileName="bad-file.zip"
        status="FAILED"
        progressPercent={0}
        error="File too large"
      />
    );

    expect(screen.getByText('File too large')).toBeInTheDocument();
  });

  it('shows different status labels', () => {
    const { rerender } = render(
      <AttachmentProgress
        fileName="test.txt"
        status="PENDING"
        progressPercent={0}
      />
    );

    expect(screen.getByText('Pending')).toBeInTheDocument();

    rerender(
      <AttachmentProgress
        fileName="test.txt"
        status="DOWNLOADING"
        progressPercent={30}
      />
    );

    expect(screen.getByText('Downloading')).toBeInTheDocument();
  });
});