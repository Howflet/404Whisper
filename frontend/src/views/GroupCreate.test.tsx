import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import GroupCreate from '../views/GroupCreate';
import { vi } from 'vitest';

describe('GroupCreate', () => {
  const mockOnClose = vi.fn();
  const mockOnCreated = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders group creation form', () => {
    render(<GroupCreate onClose={mockOnClose} onCreated={mockOnCreated} />);

    expect(screen.getByText('Create New Group')).toBeInTheDocument();
    expect(screen.getByLabelText('Group Name *')).toBeInTheDocument();
    expect(screen.getByLabelText('Members (optional)')).toBeInTheDocument();
  });

  it('closes modal when close button is clicked', () => {
    render(<GroupCreate onClose={mockOnClose} onCreated={mockOnCreated} />);

    const closeBtn = screen.getByText('✕');
    fireEvent.click(closeBtn);

    expect(mockOnClose).toHaveBeenCalled();
  });

  it('closes modal when cancel is clicked', () => {
    render(<GroupCreate onClose={mockOnClose} onCreated={mockOnCreated} />);

    const cancelBtn = screen.getByText('Cancel');
    fireEvent.click(cancelBtn);

    expect(mockOnClose).toHaveBeenCalled();
  });

  it('requires group name', async () => {
    render(<GroupCreate onClose={mockOnClose} onCreated={mockOnCreated} />);

    const submitBtn = screen.getByText('Create Group');
    expect(submitBtn).toBeDisabled();

    const nameInput = screen.getByLabelText('Group Name *') as HTMLInputElement;
    await userEvent.type(nameInput, 'Test Group');

    expect(submitBtn).not.toBeDisabled();
  });

  it('validates Session ID format', async () => {
    render(<GroupCreate onClose={mockOnClose} onCreated={mockOnCreated} />);

    const nameInput = screen.getByLabelText('Group Name *');
    const memberInput = screen.getByLabelText('Members (optional)');
    const submitBtn = screen.getByText('Create Group');

    await userEvent.type(nameInput, 'Test Group');
    await userEvent.type(memberInput, 'invalid-session-id');
    fireEvent.click(submitBtn);

    expect(screen.getByText(/Invalid Session ID/)).toBeInTheDocument();
    expect(mockOnCreated).not.toHaveBeenCalled();
  });

  it('accepts comma-separated member IDs', async () => {
    const validId = '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5c';
    render(<GroupCreate onClose={mockOnClose} onCreated={mockOnCreated} />);

    const nameInput = screen.getByLabelText('Group Name *');
    const memberInput = screen.getByLabelText('Members (optional)');

    await userEvent.type(nameInput, 'Test Group');
    await userEvent.type(memberInput, `${validId}, ${validId}`);

    // Form should accept the input (no error shown yet because we're not testing API call)
    expect(memberInput).toHaveValue(`${validId}, ${validId}`);
  });
});