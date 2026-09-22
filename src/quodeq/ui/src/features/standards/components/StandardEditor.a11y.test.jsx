/**
 * #7309 - the resize divider between the standard tree and the detail panel
 * is focusable and marked role="separator", but its keydown handler only
 * called preventDefault() for ArrowLeft/ArrowRight without ever resizing.
 * This mirrors the model at features/side-pane/SidePane.a11y.test.jsx.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
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

describe('StandardEditor divider keyboard accessibility', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('divider has aria-orientation, an accessible name and a numeric value', () => {
    setup();
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);
    const divider = screen.getByRole('separator', { name: /resize tree panel/i });
    expect(divider).toHaveAttribute('aria-orientation', 'vertical');
    expect(divider).toHaveAttribute('aria-valuenow', '280');
    expect(divider).toHaveAttribute('aria-valuemin', '180');
    expect(divider).toHaveAttribute('aria-valuemax', '600');
  });

  it('ArrowRight grows the tree panel width by one step', () => {
    setup();
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);
    const divider = screen.getByRole('separator', { name: /resize tree panel/i });
    act(() => { fireEvent.keyDown(divider, { key: 'ArrowRight' }); });
    expect(divider).toHaveAttribute('aria-valuenow', '296');
  });

  it('ArrowLeft shrinks the tree panel width by one step', () => {
    setup();
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);
    const divider = screen.getByRole('separator', { name: /resize tree panel/i });
    act(() => { fireEvent.keyDown(divider, { key: 'ArrowLeft' }); });
    expect(divider).toHaveAttribute('aria-valuenow', '264');
  });
});
