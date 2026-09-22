import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ProjectPathContent } from './ProjectPathContent.jsx';

function relocatingActions() {
  return {
    relocating: 'p1',
    relocatePath: '',
    relocateError: null,
    setRelocatePath: vi.fn(),
    submitRelocate: vi.fn(),
    setRelocating: vi.fn(),
    startRelocate: vi.fn(),
  };
}

describe('ProjectPathContent relocate input accessibility', () => {
  it('has an accessible name so screen reader users know its purpose', () => {
    render(
      <ProjectPathContent
        id="p1"
        p={{ location: 'local', path: '/old/path', pathExists: false }}
        relocateActions={relocatingActions()}
      />,
    );
    expect(screen.getByRole('textbox', { name: 'New project path' })).toBeInTheDocument();
  });
});
