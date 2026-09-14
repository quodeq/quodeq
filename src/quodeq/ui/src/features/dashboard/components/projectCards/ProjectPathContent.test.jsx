import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ProjectPathContent } from './ProjectPathContent.jsx';

// Cluster 25: the copy control used to call navigator.clipboard.writeText
// directly, bypassing the safe copyToClipboard wrapper (no .catch at all).
// It must now route through copyToClipboard.

function noopRelocateActions() {
  return {
    relocating: null,
    relocatePath: '',
    relocateError: null,
    setRelocatePath: vi.fn(),
    submitRelocate: vi.fn(),
    setRelocating: vi.fn(),
    startRelocate: vi.fn(),
  };
}

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

describe('ProjectPathContent', () => {
  it('copying an online project path calls navigator.clipboard.writeText via copyToClipboard', () => {
    render(
      <ProjectPathContent
        id="p1"
        p={{ location: 'online', path: '/repo/online-path' }}
        relocateActions={noopRelocateActions()}
      />,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('/repo/online-path');
  });

  it('a rejected copy does not throw (copyToClipboard swallows and warns)', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } });
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    render(
      <ProjectPathContent
        id="p1"
        p={{ location: 'online', path: '/repo/online-path' }}
        relocateActions={noopRelocateActions()}
      />,
    );
    expect(() => fireEvent.click(screen.getByRole('button'))).not.toThrow();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });
});
