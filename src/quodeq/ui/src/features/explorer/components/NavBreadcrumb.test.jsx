import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import NavBreadcrumb, { labelFor } from './NavBreadcrumb.jsx';

// Map drill-down entries carry their folder path as a route param (see
// App.jsx's map renderer); the crumb must read as the folder name so the
// trail reads map / src / components instead of map / map / map.
describe('labelFor — map drill-down entries', () => {
  it('root map entry (no path) keeps the tab label', () => {
    expect(labelFor({ page: 'map' })).toBe('map');
    expect(labelFor({ page: 'map', path: '' })).toBe('map');
  });

  it('a drill-down entry shows the deepest folder name', () => {
    expect(labelFor({ page: 'map', path: 'src' })).toBe('src');
    expect(labelFor({ page: 'map', path: 'src/components' })).toBe('components');
  });

  it('tolerates trailing slashes in the path', () => {
    expect(labelFor({ page: 'map', path: 'src/app/' })).toBe('app');
  });

  it('violations entries keep their tab label regardless of the sub-tab param', () => {
    expect(labelFor({ page: 'violations', subTab: 'dismissed' })).toBe('violations');
  });
});

describe('NavBreadcrumb project crumb', () => {
  const stack = [{ page: 'violations' }];

  it('renders the project root as a clickable button when projectName and onSelectProject are given', () => {
    render(
      <NavBreadcrumb
        stack={stack}
        onGoTo={() => {}}
        projectName="my-project"
        onSelectProject={() => {}}
      />
    );
    expect(screen.getByRole('button', { name: 'my-project' })).toBeInTheDocument();
  });

  it('calls onSelectProject when the project crumb is clicked', () => {
    const onSelectProject = vi.fn();
    render(
      <NavBreadcrumb
        stack={stack}
        onGoTo={() => {}}
        projectName="my-project"
        onSelectProject={onSelectProject}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'my-project' }));
    expect(onSelectProject).toHaveBeenCalledTimes(1);
  });

  it('marks the project crumb with the --project class and keeps it clickable even as the only stack tab', () => {
    const { container } = render(
      <NavBreadcrumb
        stack={[{ page: 'projects' }]}
        onGoTo={() => {}}
        projectName="my-project"
        onSelectProject={() => {}}
      />
    );
    const projectCrumb = container.querySelector('.nav-breadcrumb__crumb--project');
    expect(projectCrumb).not.toBeNull();
    expect(projectCrumb.querySelector('button')).not.toBeNull();
  });

  it('renders the project crumb as non-clickable text when onSelectProject is absent (backward compatible)', () => {
    render(<NavBreadcrumb stack={stack} onGoTo={() => {}} projectName="my-project" />);
    expect(screen.getByText('my-project').tagName).toBe('SPAN');
    expect(screen.queryByRole('button', { name: 'my-project' })).toBeNull();
  });

  it('renders no project crumb when projectName is falsy', () => {
    const { container } = render(
      <NavBreadcrumb stack={stack} onGoTo={() => {}} onSelectProject={() => {}} />
    );
    expect(container.querySelector('.nav-breadcrumb__crumb--project')).toBeNull();
    expect(screen.queryByText('my-project')).toBeNull();
  });
});

describe('NavBreadcrumb collapse and jump bar', () => {
  it('collapses deep paths behind a "…" chip whose menu lists hidden ancestors', () => {
    const onGoTo = vi.fn();
    render(
      <NavBreadcrumb
        stack={[
          { page: 'violations' },
          { page: 'explorer', dimension: 'Security' },
          { page: 'principle', label: 'modularity' },
          { page: 'file', label: 'HomeVC.swift' },
        ]}
        onGoTo={onGoTo}
        projectName="repo"
        onSelectProject={() => {}}
      />
    );
    // repo / … / modularity / HomeVC.swift — the middle is one click away
    expect(screen.queryByText('violations')).toBeNull();
    expect(screen.queryByText('security')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show hidden path segments' }));
    expect(screen.getByRole('menuitem', { name: 'security' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('menuitem', { name: 'violations' }));
    expect(onGoTo).toHaveBeenCalledWith(0);
  });

  it('drops intermediate run-date segments from the visible path but keeps them reachable', () => {
    render(
      <NavBreadcrumb
        stack={[
          { page: 'history' },
          { page: 'history-run', dateLabel: '28 jul 2026' },
          { page: 'explorer', dimension: 'Security' },
        ]}
        onGoTo={() => {}}
        projectName="repo"
        onSelectProject={() => {}}
      />
    );
    expect(screen.queryByText('28 jul 2026')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show hidden path segments' }));
    expect(screen.getByRole('menuitem', { name: '28 jul 2026' })).toBeInTheDocument();
  });

  it('opens a sibling menu with the current item marked when siblingsFor supplies one', () => {
    const onSelect = vi.fn();
    const siblingsFor = (entry) => (entry.page === 'explorer'
      ? [
          { key: 'Security', label: 'security', current: true, onSelect: () => {} },
          { key: 'Maintainability', label: 'maintainability', current: false, onSelect },
        ]
      : null);
    render(
      <NavBreadcrumb
        stack={[{ page: 'violations' }, { page: 'explorer', dimension: 'Security' }]}
        onGoTo={() => {}}
        projectName="repo"
        onSelectProject={() => {}}
        siblingsFor={siblingsFor}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'security' }));
    expect(screen.getByRole('menuitemradio', { name: 'security' })).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'maintainability' }));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  const deeperPageProps = (overrides = {}) => ({
    stack: [
      { page: 'violations' },
      { page: 'explorer', dimension: 'Security' },
      { page: 'file', label: 'HomeVC.swift' },
    ],
    onGoTo: () => {},
    projectName: 'repo',
    onSelectProject: () => {},
    siblingsFor: (entry) => (entry.page === 'explorer'
      ? [
          { key: 'Security', label: 'security', current: true, onSelect: () => {} },
          { key: 'Maintainability', label: 'maintainability', current: false, onSelect: () => {} },
        ]
      : null),
    ...overrides,
  });

  it('navigates straight back to the level when an earlier menu crumb is clicked', () => {
    // Address-bar behaviour: a plain click on an ancestor walks back; the
    // sibling menu is NOT what a left click opens.
    const onGoTo = vi.fn();
    render(<NavBreadcrumb {...deeperPageProps({ onGoTo })} />);
    fireEvent.click(screen.getByRole('button', { name: 'security' }));
    expect(onGoTo).toHaveBeenCalledWith(1);
    expect(screen.queryByRole('menuitemradio', { name: 'maintainability' })).toBeNull();
  });

  it('opens the sibling menu of an earlier crumb from its caret button', () => {
    const onGoTo = vi.fn();
    render(<NavBreadcrumb {...deeperPageProps({ onGoTo })} />);
    fireEvent.click(screen.getByRole('button', { name: 'Switch security' }));
    expect(onGoTo).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'security' }));
    expect(onGoTo).toHaveBeenCalledWith(1);
  });

  it('opens the sibling menu of an earlier crumb on right-click', () => {
    const onGoTo = vi.fn();
    render(<NavBreadcrumb {...deeperPageProps({ onGoTo })} />);
    fireEvent.contextMenu(screen.getByRole('button', { name: 'security' }));
    expect(screen.getByRole('menuitemradio', { name: 'maintainability' })).toBeInTheDocument();
    expect(onGoTo).not.toHaveBeenCalled();
  });

  it('opens the sibling menu on press-and-hold and swallows the release click', () => {
    vi.useFakeTimers();
    try {
      const onGoTo = vi.fn();
      render(<NavBreadcrumb {...deeperPageProps({ onGoTo })} />);
      const label = screen.getByRole('button', { name: 'security' });
      fireEvent.pointerDown(label);
      act(() => { vi.advanceTimersByTime(500); });
      fireEvent.pointerUp(label);
      fireEvent.click(label);
      expect(screen.getByRole('menuitemradio', { name: 'maintainability' })).toBeInTheDocument();
      expect(onGoTo).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('a released press shorter than the hold threshold still navigates', () => {
    vi.useFakeTimers();
    try {
      const onGoTo = vi.fn();
      render(<NavBreadcrumb {...deeperPageProps({ onGoTo })} />);
      const label = screen.getByRole('button', { name: 'security' });
      fireEvent.pointerDown(label);
      act(() => { vi.advanceTimersByTime(200); });
      fireEvent.pointerUp(label);
      fireEvent.click(label);
      expect(onGoTo).toHaveBeenCalledWith(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('stays a plain link when siblingsFor returns null for the level', () => {
    const onGoTo = vi.fn();
    render(
      <NavBreadcrumb
        stack={[{ page: 'violations' }, { page: 'explorer', dimension: 'Security' }]}
        onGoTo={onGoTo}
        projectName="repo"
        onSelectProject={() => {}}
        siblingsFor={() => null}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'violations' }));
    expect(onGoTo).toHaveBeenCalledWith(0);
  });
});
