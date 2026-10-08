import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Pretext does off-DOM canvas measurement, which jsdom can't do and which is
// irrelevant to the rendered text content we assert here.
vi.mock('../utils/pretext.js', () => ({
  measureWidth: () => 0,
  cssFontFromElement: () => '12px monospace',
}));

import ContextBlock from './ContextBlock.jsx';

// The backend marks the violation line with ">>> " (marker + separator space).
// The highlighted line's real indentation is 4 spaces here.
const context = [
  'def hello():',
  ">>>     print('hi')",
  '    return 1',
].join('\n');

function textOf(el) {
  // Mirror what the user sees; white-space: pre preserves leading spaces,
  // and textContent is independent of CSS so it's a faithful check.
  return el.textContent;
}

describe('ContextBlock highlighted-line indentation', () => {
  it('strips the marker + separator so the highlighted line is not over-indented', () => {
    const { container } = render(<ContextBlock context={context} line={42} />);
    // Scope bar is collapsed by default — expand it to render the code.
    fireEvent.click(screen.getByText(/See code/));

    const hl = container.querySelector('.ctx-line--hl .ctx-code');
    expect(hl).not.toBeNull();
    // 4 spaces, NOT 5. The old slice(3) left the separator space behind.
    expect(textOf(hl)).toBe("    print('hi')");
  });

  it('highlighted indentation matches an identical unmarked line', () => {
    const { container } = render(<ContextBlock context={context} line={42} />);
    fireEvent.click(screen.getByText(/See code/));

    const codeCells = [...container.querySelectorAll('.ctx-code')].map(textOf);
    const highlighted = textOf(container.querySelector('.ctx-line--hl .ctx-code'));
    // The 'return 1' context line and the highlighted 'print' line share the
    // same 4-space indentation depth.
    const returnLine = codeCells.find((t) => t.includes('return 1'));
    const hlIndent = highlighted.match(/^ */)[0].length;
    const returnIndent = returnLine.match(/^ */)[0].length;
    expect(hlIndent).toBe(returnIndent);
  });
});

describe('ContextBlock editor-tab strip', () => {
  it('names the file and its line while collapsed, without rendering code', () => {
    const { container } = render(<ContextBlock context={context} line={42} file="src/app/hello.py" />);
    const toggle = screen.getByRole('button', { expanded: false });
    expect(toggle).toHaveTextContent('src/app/hello.py:42');
    expect(toggle).toHaveTextContent('L37-39 · 3 lines');
    expect(container.querySelector('.ctx-line')).toBeNull();
  });

  it('opens the code when the strip is clicked', () => {
    const { container } = render(<ContextBlock context={context} line={42} file="src/app/hello.py" />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));
    expect(screen.getByRole('button', { expanded: true })).toBeInTheDocument();
    expect(container.querySelectorAll('.ctx-line')).toHaveLength(3);
  });

  it('takes the line from a file ref that carries its own suffix', () => {
    render(<ContextBlock snippet="x = 1" file="pkg/mod.py:7" />);
    expect(screen.getByRole('button', { expanded: false })).toHaveTextContent('pkg/mod.py:7');
  });

  it('offers a copy-path button only when the finding names a file', () => {
    const { rerender } = render(<ContextBlock context={context} line={42} file="src/app/hello.py" />);
    expect(screen.getByRole('button', { name: 'Copy path' })).toBeInTheDocument();
    rerender(<ContextBlock context={context} line={42} />);
    expect(screen.queryByRole('button', { name: 'Copy path' })).toBeNull();
    expect(screen.getByRole('button', { expanded: false })).toHaveTextContent('See code');
  });

  it('shows a check on the copy button for a beat after copying', async () => {
    vi.useFakeTimers();
    const writeText = vi.fn().mockResolvedValue();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    try {
      render(<ContextBlock context={context} line={42} file="src/app/hello.py" />);
      await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy path' })); });
      expect(writeText).toHaveBeenCalledWith('src/app/hello.py:42');
      expect(screen.getByRole('button', { name: 'Copied' })).toHaveClass('code-tab-copy--copied');
      act(() => { vi.advanceTimersByTime(1500); });
      expect(screen.getByRole('button', { name: 'Copy path' })).not.toHaveClass('code-tab-copy--copied');
    } finally {
      vi.useRealTimers();
    }
  });

  it('says "1 line" for a single-line snippet', () => {
    render(<ContextBlock snippet="x = 1" line={3} file="a.py" />);
    expect(screen.getByRole('button', { expanded: false })).toHaveTextContent('L3 · 1 line');
  });
});
