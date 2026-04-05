import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsPanel from '../components/SettingsPanel';
import { vi } from 'vitest';

const mockProps = {
  sessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b',
  displayName: 'Alice',
  personalVibe: null as const,
  onClose: vi.fn(),
  onUpdate: vi.fn(),
};

describe('SettingsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock clipboard API
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn(() => Promise.resolve()),
      },
    });
  });

  it('renders Session ID and displays copy button', () => {
    render(<SettingsPanel {...mockProps} />);
    
    expect(screen.getByText(mockProps.sessionId)).toBeInTheDocument();
    expect(screen.getByText('Copy')).toBeInTheDocument();
  });

  it('copies Session ID when clicked', async () => {
    render(<SettingsPanel {...mockProps} />);
    
    const copyBtn = screen.getByText('Copy');
    fireEvent.click(copyBtn);
    
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(mockProps.sessionId);
    expect(screen.getByText('✓ Copied')).toBeInTheDocument();
  });

  it('displays and allows editing display name', async () => {
    render(<SettingsPanel {...mockProps} />);
    
    const input = screen.getByDisplayValue('Alice') as HTMLInputElement;
    expect(input).toBeInTheDocument();
    
    await userEvent.clear(input);
    await userEvent.type(input, 'Bob');
    
    expect(input.value).toBe('Bob');
  });

  it('calls onClose when cancel is clicked', () => {
    render(<SettingsPanel {...mockProps} />);
    
    const cancelBtn = screen.getByText('Cancel');
    fireEvent.click(cancelBtn);
    
    expect(mockProps.onClose).toHaveBeenCalled();
  });

  it('closes panel when close button is clicked', () => {
    render(<SettingsPanel {...mockProps} />);
    
    const closeBtn = screen.getByText('✕');
    fireEvent.click(closeBtn);
    
    expect(mockProps.onClose).toHaveBeenCalled();
  });
});