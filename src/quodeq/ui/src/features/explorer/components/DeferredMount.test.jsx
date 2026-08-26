import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DeferredMount from './DeferredMount.jsx';

// A param-fed detail page (principle / file) renders its whole card list
// synchronously — there is no fetch, so nothing ever painted between the
// click and the finished page and the click looked ignored. DeferredMount
// splits that into two commits: the cheap page frame with a fallback first
// (the paint that makes the navigation feel acknowledged), the heavy
// children right after.
describe('DeferredMount', () => {
  it('renders the fallback strictly before the content ever renders', () => {
    const order = [];
    function Fallback() {
      order.push('fallback');
      return <div>loading</div>;
    }
    function Content() {
      order.push('content');
      return <div>content</div>;
    }

    render(<DeferredMount fallback={<Fallback />}><Content /></DeferredMount>);

    expect(order[0]).toBe('fallback');
    expect(order).toContain('content');
    expect(order.indexOf('fallback')).toBeLessThan(order.indexOf('content'));
  });

  it('settles on the content with the fallback unmounted', () => {
    render(
      <DeferredMount fallback={<div>loading</div>}>
        <div>content</div>
      </DeferredMount>
    );

    expect(screen.getByText('content')).toBeInTheDocument();
    expect(screen.queryByText('loading')).toBeNull();
  });
});
