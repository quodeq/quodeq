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

// Compare ranks projects against each other, so the tab only exists once at
// least two projects are analyzed — the parent computes that and passes
// showCompareTab. When shown it sits directly below overview.
describe('Sidebar compare nav item — fleet gating', () => {
  it('is hidden by default (fewer than two analyzed projects)', () => {
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} />);
    expect(screen.queryByTitle('compare')).toBeNull();
  });

  it('shows directly below overview when showCompareTab is set', () => {
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} showCompareTab />);
    const labels = [...document.querySelectorAll('.sidebar-nav-item .sidebar-nav-label')]
      .map((el) => el.textContent);
    expect(labels.indexOf('compare')).toBe(labels.indexOf('overview') + 1);
  });

  it('still shows when the project tabs are hidden (selected project has no runs)', () => {
    render(<Sidebar activeTab="compare" onNavTab={vi.fn()} showProjectTabs={false} showCompareTab />);
    expect(screen.getByTitle('compare')).toBeInTheDocument();
    expect(screen.queryByTitle('overview')).toBeNull();
  });

  it('the violations badge says what it counts: majors', () => {
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} violationsCount={5} />);
    expect(screen.getByText('5')).toHaveAttribute('title', '5 majors');
  });

  it('one major is singular', () => {
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} violationsCount={1} />);
    expect(screen.getByText('1')).toHaveAttribute('title', '1 major');
  });
});

describe('Sidebar active nav item', () => {
  it('marks the active tab with aria-current so assistive tech announces it', () => {
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} />);
    const current = screen.getAllByRole('button').filter((b) => b.getAttribute('aria-current') === 'page');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveClass('active');
  });

  it('inactive tabs carry no aria-current', () => {
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} />);
    const inactive = screen.getAllByRole('button').filter((b) => !b.classList.contains('active'));
    expect(inactive.length).toBeGreaterThan(0);
    inactive.forEach((b) => expect(b).not.toHaveAttribute('aria-current'));
  });
});
