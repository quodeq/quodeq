import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ProjectsPage from './ProjectsPage.jsx';

describe('ProjectsPage', () => {
  it('renders a "setup incomplete" badge on online-location projects', () => {
    const projects = [
      { id: 'a', name: 'local-one', location: 'local' },
      { id: 'b', name: 'online-legacy', location: 'online' },
    ];
    render(<ProjectsPage projects={projects} actions={{}} />);
    const badges = screen.queryAllByText(/setup incomplete/i);
    expect(badges).toHaveLength(1);
  });

  it('renders no badge when all projects are local', () => {
    const projects = [
      { id: 'a', name: 'one', location: 'local' },
      { id: 'b', name: 'two', location: 'local' },
    ];
    render(<ProjectsPage projects={projects} actions={{}} />);
    expect(screen.queryByText(/setup incomplete/i)).not.toBeInTheDocument();
  });
});
