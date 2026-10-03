import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import FadeIn from './FadeIn.jsx';

// The fade restarts through an alternating data attribute instead of a keyed
// remount, which would drop the children's state and refire mount effects.
describe('FadeIn', () => {
  it('keeps the same DOM node across key changes and alternates the phase', () => {
    const { container, rerender } = render(<FadeIn restartKey="one" className="x"><span>page</span></FadeIn>);
    const node = container.firstChild;
    expect(node).toHaveAttribute('data-fade', 'a');
    expect(node).toHaveClass('x');

    rerender(<FadeIn restartKey="two" className="x"><span>page</span></FadeIn>);
    expect(container.firstChild).toBe(node);
    expect(node).toHaveAttribute('data-fade', 'b');

    rerender(<FadeIn restartKey="three" className="x"><span>page</span></FadeIn>);
    expect(container.firstChild).toBe(node);
    expect(node).toHaveAttribute('data-fade', 'a');
  });

  it('does not restart when the key stays the same', () => {
    const key = {};
    const { container, rerender } = render(<FadeIn restartKey={key}><span>a</span></FadeIn>);
    rerender(<FadeIn restartKey={key}><span>b</span></FadeIn>);
    expect(container.firstChild).toHaveAttribute('data-fade', 'a');
  });

  it('ignores a nullish key so a pending gap restarts the fade once, when content lands', () => {
    const { container, rerender } = render(<FadeIn restartKey="one"><span>a</span></FadeIn>);
    rerender(<FadeIn restartKey={null} />);
    expect(container.firstChild).toHaveAttribute('data-fade', 'a');
    rerender(<FadeIn restartKey="two"><span>b</span></FadeIn>);
    expect(container.firstChild).toHaveAttribute('data-fade', 'b');
  });
});
