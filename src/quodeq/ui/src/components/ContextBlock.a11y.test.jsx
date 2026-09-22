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

const context = [
  'def hello():',
  ">>>     print('hi')",
  '    return 1',
].join('\n');

describe('ContextBlock violation line non-color marker', () => {
  it('gives the highlighted line a leading text marker, not only a CSS class', () => {
    const { container } = render(<ContextBlock context={context} line={42} />);
    // Scope bar is collapsed by default -- expand it to render the code.
    fireEvent.click(screen.getByText(/See code/));

    const hlLine = container.querySelector('.ctx-line--hl');
    expect(hlLine).not.toBeNull();
    expect(hlLine.textContent.startsWith('Violation on this line:')).toBe(true);
  });

  it('keeps a 5-digit line number intact next to the marker', () => {
    // The marker used to be a 12px inline-block inside the 48px gutter, which
    // left too little room for five digits.
    const { container } = render(<ContextBlock context={context} line={10042} />);
    fireEvent.click(screen.getByText(/See code/));

    const gutters = [...container.querySelectorAll('.ctx-gutter')];
    const numbers = gutters.map((g) => g.textContent.replace('Violation on this line:', '').replace('▸', ''));
    expect(numbers).toEqual(['10037', '10038', '10039']);
    const marker = container.querySelector('.ctx-line--hl .context-line__marker');
    expect(marker.parentElement.classList.contains('ctx-gutter')).toBe(true);
  });
});
