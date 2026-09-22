import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ViolationsSubTabContent } from './ViolationsPage.jsx';

// Shared projects have no mutation route on the backend (dismiss/restore/
// delete are local-only by design, and the same project id can exist in both
// worlds). ViolationsSubTabContent is the App-adjacent wiring point between
// useDismissedFindings' handlers and DismissedSubTab's action buttons: when
// selectedSource is 'shared' it must pass undefined instead of the real
// handlers so the buttons vanish while the dismissed list stays visible.
const sampleA = { req: 'A1', file: 'a.py', line: 10, severity: 'minor', principle: 'P1' };
const sampleB = { req: 'B1', file: 'b.py', line: 20, severity: 'major', principle: 'P2' };

function renderDismissedSubTab(selectedSource, overrides = {}) {
  const handlers = {
    handleRestore: vi.fn(),
    handleRestoreAll: vi.fn(),
    handleDelete: vi.fn(),
    handleDeleteAll: vi.fn(),
    ...overrides,
  };
  render(
    <ViolationsSubTabContent
      activeSubTab="dismissed"
      dismissed={[sampleA, sampleB]}
      visibleDimensions={[]}
      callbacks={{}}
      fileCurrentPath=""
      setFileCurrentPath={() => {}}
      selectedSource={selectedSource}
      {...handlers}
    />
  );
  return handlers;
}

describe('ViolationsSubTabContent — dismissed sub-tab, source gating', () => {
  it('shows Restore/Delete and Restore all/Delete all when source is local', () => {
    renderDismissedSubTab('local');
    expect(screen.getAllByRole('button', { name: 'Restore' })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: 'Delete' })).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Restore all' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete all' })).toBeInTheDocument();
  });

  it('hides every action button when source is shared, but keeps the list visible', () => {
    renderDismissedSubTab('shared');
    expect(screen.queryByRole('button', { name: 'Restore' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Restore all' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete all' })).toBeNull();
    expect(screen.getByText('a.py:10')).toBeInTheDocument();
    expect(screen.getByText('b.py:20')).toBeInTheDocument();
  });

  it('renders the empty message instead of DismissedSubTab when there are no dismissed findings', () => {
    render(
      <ViolationsSubTabContent
        activeSubTab="dismissed"
        dismissed={[]}
        visibleDimensions={[]}
        callbacks={{}}
        fileCurrentPath=""
        setFileCurrentPath={() => {}}
        selectedSource="shared"
        handleRestore={vi.fn()}
        handleRestoreAll={vi.fn()}
        handleDelete={vi.fn()}
        handleDeleteAll={vi.fn()}
      />
    );
    expect(screen.getByText('No dismissed violations.')).toBeInTheDocument();
  });
});
