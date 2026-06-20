/**
 * Finding #514: SidePane global pointer listeners must be cleaned up on unmount.
 *
 * Without the fix, onPointerDown adds pointermove + pointerup to window and
 * never removes them if the component unmounts mid-drag. This test proves the
 * listeners are removed when the component unmounts during an active drag.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePane } from './SidePane.jsx';
import { SidePaneProvider } from './SidePaneProvider.jsx';
import { useSidePane } from './SidePaneContext.jsx';

function spec(id, title = id) {
  return { id, type: 'report', title, render: () => <p>{`body:${id}`}</p> };
}

function Adder() {
  const { addWindow } = useSidePane();
  return <button onClick={() => addWindow(spec('w1', 'Window 1'))}>add</button>;
}

describe('SidePane drag cleanup on unmount (#514)', () => {
  let addEventSpy;
  let removeEventSpy;
  let addedListeners;
  let removedListeners;

  beforeEach(() => {
    addedListeners = [];
    removedListeners = [];

    addEventSpy = vi.spyOn(window, 'addEventListener').mockImplementation((type, handler, opts) => {
      addedListeners.push({ type, handler });
    });
    removeEventSpy = vi.spyOn(window, 'removeEventListener').mockImplementation((type, handler) => {
      removedListeners.push({ type, handler });
    });
  });

  afterEach(() => {
    addEventSpy.mockRestore();
    removeEventSpy.mockRestore();
  });

  it('removes window listeners added during pointer-down drag when component unmounts', () => {
    const { unmount, getByText, getByRole } = render(
      <SidePaneProvider>
        <Adder />
        <SidePane />
      </SidePaneProvider>
    );

    // Open the pane.
    fireEvent.click(getByText('add'));

    // Simulate pointer-down on the outer resize divider (starts the drag,
    // adds pointermove + pointerup to window).
    const divider = getByRole('separator', { name: /resize side pane/i });
    fireEvent.pointerDown(divider, { clientX: 100, preventDefault: () => {} });

    const addedTypes = addedListeners.map((l) => l.type);
    expect(addedTypes).toContain('pointermove');
    expect(addedTypes).toContain('pointerup');

    // Unmount mid-drag — listeners must be removed.
    act(() => { unmount(); });

    const removedTypes = removedListeners.map((l) => l.type);
    expect(removedTypes).toContain('pointermove');
    expect(removedTypes).toContain('pointerup');
  });
});
