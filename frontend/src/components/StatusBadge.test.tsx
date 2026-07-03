import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('renders the status label with underscores as spaces', () => {
    render(<StatusBadge status="PARTIALLY_FILLED" />);
    expect(screen.getByText('PARTIALLY FILLED')).toBeInTheDocument();
  });

  it('applies a status-specific CSS class', () => {
    render(<StatusBadge status="FILLED" />);
    expect(screen.getByText('FILLED')).toHaveClass('badge', 'badge-filled');
  });
});
