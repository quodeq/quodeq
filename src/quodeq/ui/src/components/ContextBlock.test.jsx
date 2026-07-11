import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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
