import React, { useMemo, useState } from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider } from './SidePaneProvider.jsx';
import { useSidePane } from './SidePaneContext.jsx';
import { useRegisterWindowSpec } from './useRegisterWindowSpec.js';

function Page({ id, title }) {
  const spec = useMemo(
    () => ({ id, type: 'report', title, render: () => <p>{`body:${id}`}</p> }),
    [id, title],
  );
  const { hasWindow, isAtCap, toggle } = useRegisterWindowSpec('report', spec);
  return (
    <button data-testid="page-btn" onClick={toggle} disabled={isAtCap && !hasWindow}>
      {hasWindow ? 'remove' : isAtCap ? 'cap' : 'add'}
    </button>
  );
}

function DockProbe() {
  const { windows } = useSidePane();
  return <div data-testid="dock">{windows.map((w) => w.id).join(',') || 'empty'}</div>;
}

describe('useRegisterWindowSpec', () => {
  it('toggling adds and removes the registered spec from the dock', () => {
    render(
      <SidePaneProvider>
        <Page id="p1" title="P1" />
        <DockProbe />
      </SidePaneProvider>,
    );
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
    fireEvent.click(screen.getByTestId('page-btn'));
    expect(screen.getByTestId('dock')).toHaveTextContent('p1');
    fireEvent.click(screen.getByTestId('page-btn'));
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
  });

  it('isAtCap is true when the dock holds MAX_WINDOWS distinct specs', () => {
    function Filler() {
      const { addWindow } = useSidePane();
      return (
        <button
          data-testid="fill"
          onClick={() => {
            addWindow({ id: 'x1', type: 'report', title: 'x1', render: () => null });
            addWindow({ id: 'x2', type: 'report', title: 'x2', render: () => null });
            addWindow({ id: 'x3', type: 'report', title: 'x3', render: () => null });
          }}
        >fill</button>
      );
    }
    render(
      <SidePaneProvider>
        <Filler />
        <Page id="p1" title="P1" />
      </SidePaneProvider>,
    );
    fireEvent.click(screen.getByTestId('fill'));
    expect(screen.getByTestId('page-btn')).toHaveTextContent('cap');
    expect(screen.getByTestId('page-btn')).toBeDisabled();
  });

  it('unmounting the page unregisters the spec but does not close existing windows', () => {
    function ToggleVisible() {
      const [v, setV] = useState(true);
      return (
        <>
          <button data-testid="hide" onClick={() => setV(false)}>hide</button>
          {v && <Page id="p1" title="P1" />}
        </>
      );
    }
    render(
      <SidePaneProvider>
        <ToggleVisible />
        <DockProbe />
      </SidePaneProvider>,
    );
    fireEvent.click(screen.getByTestId('page-btn'));
    expect(screen.getByTestId('dock')).toHaveTextContent('p1');
    act(() => { fireEvent.click(screen.getByTestId('hide')); });
    expect(screen.getByTestId('dock')).toHaveTextContent('p1');
  });

  it('passing a null spec leaves nothing registered and toggle is a no-op', () => {
    function NullPage() {
      const { hasWindow, toggle } = useRegisterWindowSpec('report', null);
      return (
        <button data-testid="null-btn" onClick={toggle}>
          {hasWindow ? 'remove' : 'add'}
        </button>
      );
    }
    render(
      <SidePaneProvider>
        <NullPage />
        <DockProbe />
      </SidePaneProvider>,
    );
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
    fireEvent.click(screen.getByTestId('null-btn'));
    expect(screen.getByTestId('dock')).toHaveTextContent('empty');
  });

  function VersionedPage({ id, version }) {
    const spec = useMemo(
      () => ({ id, type: 'report', title: `v${version}`, render: () => <p>{`body:${version}`}</p> }),
      [id, version],
    );
    useRegisterWindowSpec('report', spec);
    return null;
  }

  function VersionedHarness() {
    const [version, setVersion] = useState(1);
    return (
      <>
        <VersionedPage id="r1" version={version} />
        <button data-testid="bump" onClick={() => setVersion((n) => n + 1)}>bump</button>
      </>
    );
  }

  function DockBody() {
    const { windows } = useSidePane();
    return <div data-testid="dock-body">{windows.map((w) => `${w.id}:${w.title}`).join(',') || 'empty'}</div>;
  }

  it('re-registering an updated spec updates the docked window in place', () => {
    function Adder() {
      const { addWindow } = useSidePane();
      return (
        <button
          data-testid="open"
          onClick={() => addWindow({ id: 'r1', type: 'report', title: 'v1', render: () => <p>body:1</p> })}
        >open</button>
      );
    }
    render(
      <SidePaneProvider>
        <Adder />
        <VersionedHarness />
        <DockBody />
      </SidePaneProvider>,
    );
    fireEvent.click(screen.getByTestId('open'));
    expect(screen.getByTestId('dock-body')).toHaveTextContent('r1:v1');
    fireEvent.click(screen.getByTestId('bump'));
    expect(screen.getByTestId('dock-body')).toHaveTextContent('r1:v2');
  });

  it('re-registering a spec when no matching window is docked does not add a window', () => {
    render(
      <SidePaneProvider>
        <VersionedHarness />
        <DockBody />
      </SidePaneProvider>,
    );
    expect(screen.getByTestId('dock-body')).toHaveTextContent('empty');
    fireEvent.click(screen.getByTestId('bump'));
    expect(screen.getByTestId('dock-body')).toHaveTextContent('empty');
  });

  it('re-registering the same spec reference does not trigger a render cascade', () => {
    let renderCount = 0;
    function CountingPage({ spec }) {
      useRegisterWindowSpec('report', spec);
      renderCount += 1;
      return null;
    }
    function Harness() {
      const spec = useMemo(
        () => ({ id: 'r1', type: 'report', title: 'v1', render: () => <p>body</p> }),
        [],
      );
      const { addWindow } = useSidePane();
      return (
        <>
          <CountingPage spec={spec} />
          <button data-testid="open" onClick={() => addWindow(spec)}>open</button>
        </>
      );
    }
    render(
      <SidePaneProvider>
        <Harness />
      </SidePaneProvider>,
    );
    const before = renderCount;
    fireEvent.click(screen.getByTestId('open'));
    const after = renderCount;
    // Opening the window should cause at most one extra render of the page
    // (the windows state changes once). If replaceWindow does not short-
    // circuit on identity, this triggers an unbounded cascade and the diff
    // will be much larger.
    expect(after - before).toBeLessThanOrEqual(2);
  });

  it('a fresh spec object on every parent render does not loop the provider', () => {
    // Mirrors the production hazard: AccumulatedOverviewPanel etc. recompute
    // their spec on every render (it closes over filtered data refs that
    // flip each render). The old hook called registerSpec/replaceWindow on
    // every render, looping with SidePaneProvider's setState until React
    // tripped its "Maximum update depth" guard.
    let pageRenderCount = 0;
    function ChurningPage() {
      // Brand new object every render — no useMemo. Same id+title across renders.
      const spec = { id: 'r1', type: 'report', title: 'stable', render: () => <p>body</p> };
      useRegisterWindowSpec('report', spec);
      pageRenderCount += 1;
      return null;
    }
    function ParentBumper() {
      const [, setN] = useState(0);
      return (
        <>
          <ChurningPage />
          <button data-testid="bump-parent" onClick={() => setN((n) => n + 1)}>bump</button>
        </>
      );
    }
    render(
      <SidePaneProvider>
        <ParentBumper />
      </SidePaneProvider>,
    );
    const start = pageRenderCount;
    // 5 parent re-renders. Each gives ChurningPage a new spec ref. If the
    // hook re-registered on every spec change, every parent bump would
    // ripple back as another render (and several more in StrictMode).
    for (let i = 0; i < 5; i += 1) {
      fireEvent.click(screen.getByTestId('bump-parent'));
    }
    const delta = pageRenderCount - start;
    // 5 forced renders + at most ~1 extra per from StrictMode double-invoke.
    expect(delta).toBeLessThanOrEqual(12);
  });
});
