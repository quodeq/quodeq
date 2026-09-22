import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ProjectsToolbar } from './ProjectsToolbar.jsx';

const baseProps = {
  filters: { query: '', location: 'all', sort: 'activity' },
  onFiltersChange: () => {},
  configured: true,
  lastSynced: Date.now(),
  stale: false,
  error: null,
};

describe('ProjectsToolbar', () => {
  it('refresh button does not call onRefresh while already refreshing', () => {
    const onRefresh = vi.fn();
    render(<ProjectsToolbar {...baseProps} refreshing onRefresh={onRefresh} />);
    fireEvent.click(screen.getByLabelText(/refresh/i));
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('refresh button calls onRefresh when not refreshing', () => {
    const onRefresh = vi.fn();
    render(<ProjectsToolbar {...baseProps} refreshing={false} onRefresh={onRefresh} />);
    fireEvent.click(screen.getByLabelText(/refresh/i));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
