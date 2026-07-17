import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import Sidebar from './Sidebar.jsx';

// Evaluation is local-only (no shared mutation route on the backend). The
// TopBar's Evaluate button is already gated on source (see App.jsx /
// TopBar.jsx), but the sidebar has its own, separate "evaluate" nav item that
// was not gated — a shared project's id can collide with a local one by
// design, so starting an evaluation from this second entry point would write
// a real run into the LOCAL project's store under that id.
describe('Sidebar evaluate nav item — source gating', () => {
  it('shows the evaluate nav item for a local selection (default)', () => {
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} selectedSource="local" />);
    expect(screen.getByTitle('evaluate')).toBeInTheDocument();
  });

  it('omits the evaluate nav item for a shared selection', () => {
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} selectedSource="shared" />);
    expect(screen.queryByTitle('evaluate')).toBeNull();
  });

  it('defaults to local (evaluate shown) when selectedSource is not passed', () => {
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} />);
    expect(screen.getByTitle('evaluate')).toBeInTheDocument();
  });
});
