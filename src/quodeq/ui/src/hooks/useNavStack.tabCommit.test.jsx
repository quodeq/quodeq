import { Suspense } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useNavStack } from './useNavStack.js';

// A tab click paints the target page in the very next commit; a push into a
// detail page renders in a transition and shows the pending bar. The two are
// told apart through an already-mounted Suspense boundary around the routed
// page: React holds the old page on screen while a transition is suspended
// inside it, but a synchronous update swaps to the boundary's fallback.

const NEVER = new Promise(() => {});
function HeavyBody() {
  throw NEVER;
}

function Page({ page }) {
  if (page === 'overview') return <h1>overview header</h1>;
  if (page === 'map') {
    // The shape every tab page takes: frame first, heavy body behind its
    // own boundary (DeferredMount in production).
    return (
      <>
        <h1>map header</h1>
        <Suspense fallback={<div>map skeleton</div>}>
          <HeavyBody />
        </Suspense>
      </>
    );
  }
  return <HeavyBody />;
}

function makeHistory() {
  return { pushState: vi.fn(), replaceState: vi.fn(), back: vi.fn(), go: vi.fn() };
}

function Shell({ onReady }) {
  const nav = useNavStack({ historyAdapter: makeHistory() });
  onReady(nav);
  const top = nav.navStack[nav.navStack.length - 1];
  return (
    <>
      {nav.navPending && <div data-testid="pending" />}
      <Suspense fallback={<div>route fallback</div>}>
        <Page page={top.page} />
      </Suspense>
    </>
  );
}

function renderShell() {
  let nav;
  render(<Shell onReady={(n) => { nav = n; }} />);
  return () => nav;
}

describe('useNavStack commit timing', () => {
  it('navTab commits synchronously: the target page frame is in the DOM after the first commit', () => {
    const nav = renderShell();
    act(() => { nav().navTab('map'); });
    expect(screen.getByText('map header')).toBeInTheDocument();
    expect(screen.getByText('map skeleton')).toBeInTheDocument();
    expect(screen.queryByText('overview header')).toBeNull();
    expect(screen.queryByTestId('pending')).toBeNull();
  });

  it('navTab does not hold the old page while the new one suspends', () => {
    const nav = renderShell();
    act(() => { nav().navTab('explorer'); });
    expect(screen.getByText('route fallback')).toBeInTheDocument();
    // React keeps the suspended content in the DOM but hides it.
    expect(screen.getByText('overview header')).not.toBeVisible();
  });

  it('navPush stays a transition: the old page holds and the pending bar shows', () => {
    const nav = renderShell();
    act(() => { nav().navPush({ page: 'explorer' }); });
    expect(screen.getByText('overview header')).toBeInTheDocument();
    expect(screen.queryByText('route fallback')).toBeNull();
    expect(screen.getByTestId('pending')).toBeInTheDocument();
  });
});
