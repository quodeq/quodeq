/**
 * The resize divider's mousedown handler sets document.body.style.cursor
 * and userSelect for the drag. If the editor unmounts mid-drag (e.g. the
 * user navigates away before releasing the mouse), those body styles were
 * never cleared because only mouseup did the cleanup.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

vi.mock('../hooks/useStandardDetail.js', () => ({
  useStandardDetail: vi.fn(),
}));

vi.mock('../hooks/useStandardsOverrides.js', () => ({
  useStandardsOverrides: vi.fn(),
}));

vi.mock('../../../hooks/useAppState.js', () => ({
  useAppState: vi.fn(),
}));

import StandardEditor from './StandardEditor.jsx';
import { setup } from './_standardEditor.fixtures.js';

describe('StandardEditor drag cleanup on unmount', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('resets body drag styles when unmounted mid-drag', () => {
    setup();
    const { unmount } = render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);
    fireEvent.mouseDown(screen.getByRole('separator'));
    expect(document.body.style.cursor).toBe('col-resize');
    unmount();
    expect(document.body.style.cursor).toBe('');
    expect(document.body.style.userSelect).toBe('');
  });
});
