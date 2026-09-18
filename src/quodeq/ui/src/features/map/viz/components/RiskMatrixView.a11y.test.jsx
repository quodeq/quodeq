/**
 * Accessibility tests for RiskMatrixView.
 * 6507: the leaf file bubble only had mouse handlers, so onFileClick was
 * unreachable from the keyboard and the bubble had no accessible name.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RiskMatrixView from './RiskMatrixView.jsx';

const NODE = {
  path: 'root/',
  name: 'root',
  isFile: false,
  violations: 0,
  compliance: 0,
  severity: {},
  children: [
    {
      path: 'root/a/',
      name: 'a',
      isFile: false,
      violations: 3,
      compliance: 1,
      severity: { critical: 1, major: 1, minor: 1 },
      children: [{}],
    },
    {
      path: 'root/b.js',
      name: 'b.js',
      isFile: true,
      violations: 2,
      compliance: 0,
      severity: { critical: 0, major: 2, minor: 0 },
      children: [],
    },
  ],
};

function fileBubble(container) {
  return container.querySelector('path[role="button"]');
}

describe('RiskMatrixView file bubble keyboard activation (6507)', () => {
  it('names the file bubble with its file and violation count', () => {
    render(<RiskMatrixView node={NODE} onFileClick={vi.fn()} />);
    expect(screen.getByLabelText('b.js: 2 violations')).toBeInTheDocument();
  });

  it('is focusable as a button', () => {
    const { container } = render(<RiskMatrixView node={NODE} onFileClick={vi.fn()} />);
    expect(fileBubble(container)).toHaveAttribute('tabindex', '0');
  });

  it('Space on the file bubble calls onFileClick', () => {
    const onFileClick = vi.fn();
    const { container } = render(<RiskMatrixView node={NODE} onFileClick={onFileClick} />);
    fireEvent.keyDown(fileBubble(container), { key: ' ' });
    expect(onFileClick).toHaveBeenCalledWith(expect.objectContaining({ path: 'root/b.js' }));
  });

  it('Enter on the file bubble calls onFileClick', () => {
    const onFileClick = vi.fn();
    const { container } = render(<RiskMatrixView node={NODE} onFileClick={onFileClick} />);
    fireEvent.keyDown(fileBubble(container), { key: 'Enter' });
    expect(onFileClick).toHaveBeenCalledTimes(1);
  });

  it('ignores an unrelated key on the file bubble', () => {
    const onFileClick = vi.fn();
    const { container } = render(<RiskMatrixView node={NODE} onFileClick={onFileClick} />);
    fireEvent.keyDown(fileBubble(container), { key: 'Tab' });
    expect(onFileClick).not.toHaveBeenCalled();
  });
});
