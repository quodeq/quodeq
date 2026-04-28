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
});
