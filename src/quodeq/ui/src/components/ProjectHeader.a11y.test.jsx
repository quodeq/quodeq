import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ProjectHeader from './ProjectHeader.jsx';

describe('ProjectHeader breadcrumb keyboard activation', () => {
  it('activates the parent breadcrumb with Space, not just Enter', () => {
    const onProjectChange = vi.fn();
    render(
      <ProjectHeader
        project={{ displayName: 'child', parent: 'root', parentId: 'root-id' }}
        navigation={{ onProjectChange }}
      />,
    );
    const breadcrumb = screen.getByRole('button', { name: 'root' });
    fireEvent.keyDown(breadcrumb, { key: ' ' });
    expect(onProjectChange).toHaveBeenCalledWith('root-id');
  });
});
