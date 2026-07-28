import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import NavBreadcrumb from './NavBreadcrumb.jsx';

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

  it('navigates back to the level when the current sibling is picked from a deeper page', () => {
    // Regression: from a detail page, the ancestor dimension crumb only opened
    // the sibling menu and its current item was a no-op, so there was no way
    // back up to that level.
    const onGoTo = vi.fn();
    const siblingsFor = (entry) => (entry.page === 'explorer'
      ? [
          { key: 'Security', label: 'security', current: true, onSelect: () => {} },
          { key: 'Maintainability', label: 'maintainability', current: false, onSelect: () => {} },
        ]
      : null);
    render(
      <NavBreadcrumb
        stack={[
          { page: 'violations' },
          { page: 'explorer', dimension: 'Security' },
          { page: 'file', label: 'HomeVC.swift' },
        ]}
        onGoTo={onGoTo}
        projectName="repo"
        onSelectProject={() => {}}
        siblingsFor={siblingsFor}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'security' }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'security' }));
    expect(onGoTo).toHaveBeenCalledWith(1);
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
