import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ProjectsToolbar } from './ProjectsToolbar.jsx';

const baseProps = {
  filters: { query: '', location: 'all', sort: 'activity' },
  onFiltersChange: () => {},
  configured: true,
};

describe('ProjectsToolbar', () => {
  // The sync status moved to the strip under the header (SyncStrip).
  it('has no sync indicator or refresh button of its own', () => {
    render(<ProjectsToolbar {...baseProps} />);
    expect(screen.queryByLabelText(/refresh/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/synced|syncing/)).not.toBeInTheDocument();
  });

  it('offers the location filter only when a team repository is configured', () => {
    const { rerender } = render(<ProjectsToolbar {...baseProps} />);
    expect(screen.getByRole('button', { name: /location/i })).toBeInTheDocument();
    rerender(<ProjectsToolbar {...baseProps} configured={false} />);
    expect(screen.queryByRole('button', { name: /location/i })).not.toBeInTheDocument();
  });

  it('a filter pill menu picks a value and closes on Escape or an outside press', () => {
    const onFiltersChange = vi.fn();
    render(<ProjectsToolbar {...baseProps} onFiltersChange={onFiltersChange} />);
    const sortPill = screen.getByRole('button', { name: /sort/i });
    fireEvent.click(sortPill);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    fireEvent.click(sortPill);
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    fireEvent.click(sortPill);
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'name' }));
    expect(onFiltersChange).toHaveBeenCalledWith(expect.objectContaining({ sort: 'name' }));
  });
});
