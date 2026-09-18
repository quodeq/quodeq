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
});
