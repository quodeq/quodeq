import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { TabFade } from './AppMain.jsx';

// A tab switch keeps the page wrapper mounted. The fade restarts through an
// alternating data attribute instead of a keyed remount, which used to drop
// every page's state and refire every mount effect.
describe('TabFade', () => {
  it('keeps the same DOM node across tab changes and alternates the fade phase', () => {
    const { container, rerender } = render(<TabFade activeTab="overview"><span>page</span></TabFade>);
    const node = container.firstChild;
    expect(node).toHaveAttribute('data-fade', 'a');

    rerender(<TabFade activeTab="history"><span>page</span></TabFade>);
    expect(container.firstChild).toBe(node);
    expect(node).toHaveAttribute('data-fade', 'b');

    rerender(<TabFade activeTab="violations"><span>page</span></TabFade>);
    expect(container.firstChild).toBe(node);
    expect(node).toHaveAttribute('data-fade', 'a');
  });

  it('does not restart the fade when the tab stays the same', () => {
    const { container, rerender } = render(<TabFade activeTab="overview"><span>a</span></TabFade>);
    rerender(<TabFade activeTab="overview"><span>b</span></TabFade>);
    expect(container.firstChild).toHaveAttribute('data-fade', 'a');
  });
});
