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
