/**
 * Accessibility tests for ZoomablePackView.
 * 6355: drill-down and open-file were wired to handleClick only. Every
 * non-root circle has to be a named, focusable button that reaches the same
 * handler from Enter and Space, not just the svg's Escape-to-go-up.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ZoomablePackView from './ZoomablePackView.jsx';

const NODE = {
  path: 'root/',
  name: 'root',
  isFile: false,
  violations: 5,
  compliance: 3,
  severity: {},
  children: [
    {
      path: 'root/a/',
      name: 'a',
      isFile: false,
      violations: 2,
      compliance: 1,
      severity: { critical: 1, major: 0, minor: 0 },
      children: [
        { path: 'root/a/foo.js', name: 'foo.js', isFile: true, violations: 1, compliance: 0, severity: { critical: 0, major: 1, minor: 0 } },
      ],
    },
  ],
};

function renderView(props = {}) {
  return render(
    <ZoomablePackView
      node={NODE}
      viewMode="violations"
      onDrillDown={vi.fn()}
      onFileClick={vi.fn()}
      {...props}
    />
  );
}

describe('ZoomablePackView circle keyboard activation (6355)', () => {
  it('Enter on a folder circle drills into it', () => {
    const onDrillDown = vi.fn();
    renderView({ onDrillDown });
    fireEvent.keyDown(screen.getByLabelText('a, critical violations'), { key: 'Enter' });
    expect(onDrillDown).toHaveBeenCalledWith('root/a/');
  });

  it('Space on a folder circle drills into it', () => {
    const onDrillDown = vi.fn();
    renderView({ onDrillDown });
    fireEvent.keyDown(screen.getByLabelText('a, critical violations'), { key: ' ' });
    expect(onDrillDown).toHaveBeenCalledWith('root/a/');
  });

  it('Enter on a file circle opens the file', () => {
    const onFileClick = vi.fn();
    renderView({ onFileClick });
    fireEvent.keyDown(screen.getByLabelText('foo.js, major violations'), { key: 'Enter' });
    expect(onFileClick).toHaveBeenCalledWith(expect.objectContaining({ path: 'root/a/foo.js' }));
  });

  it('every clickable circle is focusable and named', () => {
    const { container } = renderView();
    const targets = container.querySelectorAll('circle[role="button"], path[role="button"]');
    expect(targets.length).toBeGreaterThan(1);
    for (const el of targets) {
      expect(el).toHaveAttribute('tabindex', '0');
      expect(el.getAttribute('aria-label')).toBeTruthy();
    }
  });
});
