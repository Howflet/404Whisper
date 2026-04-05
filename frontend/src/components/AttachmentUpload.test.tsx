import { render, screen, fireEvent } from '@testing-library/react';
import AttachmentUpload from '../components/AttachmentUpload';
import { vi } from 'vitest';

describe('AttachmentUpload', () => {
  it('renders attachment button', () => {
    render(<AttachmentUpload onFileSelected={() => {}} />);

    expect(screen.getByRole('button', { name: /attach file/i })).toBeInTheDocument();
  });

  it('calls onFileSelected when file is selected', async () => {
    const onFileSelected = vi.fn();
    render(<AttachmentUpload onFileSelected={onFileSelected} />);

    const input = screen.getByRole('button', { name: /attach file/i });
    const fileInput = input.nextSibling as HTMLInputElement;

    const file = new File(['test content'], 'test.txt', { type: 'text/plain' });

    fireEvent.change(fileInput, { target: { files: [file] } });

    expect(onFileSelected).toHaveBeenCalledWith(file);
  });

  it('disables button when disabled prop is true', () => {
    render(<AttachmentUpload onFileSelected={() => {}} disabled={true} />);

    const button = screen.getByRole('button', { name: /attach file/i });
    expect(button).toBeDisabled();
  });

  it('does not call callback when no file is selected', () => {
    const onFileSelected = vi.fn();
    render(<AttachmentUpload onFileSelected={onFileSelected} />);

    const input = screen.getByRole('button', { name: /attach file/i });
    const fileInput = input.nextSibling as HTMLInputElement;

    fireEvent.change(fileInput, { target: { files: [] } });

    expect(onFileSelected).not.toHaveBeenCalled();
  });
});