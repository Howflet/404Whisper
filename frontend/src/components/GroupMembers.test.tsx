import { render, screen, fireEvent } from '@testing-library/react';
import GroupMembers from '../components/GroupMembers';
import { vi } from 'vitest';

const mockMembers = [
  {
    sessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5b',
    displayName: 'Alice',
    isAdmin: true,
    joinedAt: '2026-04-04T12:00:00Z',
  },
  {
    sessionId: '057aeb66e45660c3bdfb7c62706f6440226af43ec13f3b6f899c1dd4db1b8fce5c',
    displayName: 'Bob',
    isAdmin: false,
    joinedAt: '2026-04-04T12:05:00Z',
  },
];

// Mock the API
vi.mock('../api/client', () => ({
  api: {
    getGroup: vi.fn(() => Promise.resolve({
      id: 1,
      groupSessionId: '05abc...',
      name: 'Test Group',
      vibe: null,
      vibeCooldownUntil: null,
      members: mockMembers,
      createdAt: '2026-04-04T12:00:00Z',
      updatedAt: '2026-04-04T12:05:00Z',
    })),
    addGroupMembers: vi.fn(() => Promise.resolve({})),
    removeGroupMember: vi.fn(() => Promise.resolve({})),
  },
  ApiError: class ApiError extends Error {
    constructor(public code: string, public message: string) {
      super(message);
    }
  },
}));

describe('GroupMembers', () => {
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    render(<GroupMembers groupId={1} isAdmin={true} onClose={mockOnClose} />);
    expect(screen.getByText('Loading members...')).toBeInTheDocument();
  });

  it('displays members after loading', async () => {
    render(<GroupMembers groupId={1} isAdmin={true} onClose={mockOnClose} />);
    
    // Wait for members to load
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('shows admin badge for admin members', async () => {
    render(<GroupMembers groupId={1} isAdmin={true} onClose={mockOnClose} />);
    
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(screen.getByText('Admin')).toBeInTheDocument();
  });

  it('closes modal when close button is clicked', () => {
    render(<GroupMembers groupId={1} isAdmin={false} onClose={mockOnClose} />);
    
    const closeBtn = screen.getByText('✕');
    fireEvent.click(closeBtn);
    
    expect(mockOnClose).toHaveBeenCalled();
  });

  it('shows add members button for admins', async () => {
    render(<GroupMembers groupId={1} isAdmin={true} onClose={mockOnClose} />);
    
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(screen.getByText('Add Members')).toBeInTheDocument();
  });

  it('does not show add members button for non-admins', async () => {
    render(<GroupMembers groupId={1} isAdmin={false} onClose={mockOnClose} />);
    
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(screen.queryByText('Add Members')).not.toBeInTheDocument();
  });
});