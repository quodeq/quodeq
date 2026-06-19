import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePane } from './SidePane.jsx';
import { SidePaneProvider } from './SidePaneProvider.jsx';
import { useSidePane } from './SidePaneContext.jsx';

function spec(id, title = id) {
  return { id, type: 'report', title, render: () => <p>{`body:${id}`}</p> };
}

function Adder() {
  const { addWindow } = useSidePane();
  return (
    <div>
      <button onClick={() => addWindow(spec('alpha', 'Alpha'))}>add-a</button>
      <button onClick={() => addWindow(spec('beta', 'Beta'))}>add-b</button>
    </div>
  );
}

// Reads paneWidth out of context so tests can assert the real state value.
let capturedCtx = null;
function CtxCapture() {
  capturedCtx = useSidePane();
  return null;
}

describe('SidePane divider keyboard accessibility', () => {
  describe('#1909 - outer column resize divider', () => {
    it('outer resize divider has tabIndex=0', () => {
      render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
      fireEvent.click(screen.getByText('add-a'));
      const divider = screen.getByRole('separator', { name: /resize side pane/i });
      expect(divider).toHaveAttribute('tabindex', '0');
    });

    it('ArrowRight on outer divider increases paneWidth by ~16px', () => {
      capturedCtx = null;
      render(
        <SidePaneProvider>
          <CtxCapture />
          <Adder />
          <SidePane />
        </SidePaneProvider>,
      );
      fireEvent.click(screen.getByText('add-a'));
      const divider = screen.getByRole('separator', { name: /resize side pane/i });
      const widthBefore = capturedCtx.paneWidth;
      act(() => { fireEvent.keyDown(divider, { key: 'ArrowRight' }); });
      expect(capturedCtx.paneWidth).toBeGreaterThan(widthBefore);
    });

    it('ArrowLeft on outer divider decreases paneWidth by ~16px', () => {
      capturedCtx = null;
      render(
        <SidePaneProvider>
          <CtxCapture />
          <Adder />
          <SidePane />
        </SidePaneProvider>,
      );
      fireEvent.click(screen.getByText('add-a'));
      const divider = screen.getByRole('separator', { name: /resize side pane/i });
      const widthBefore = capturedCtx.paneWidth;
      act(() => { fireEvent.keyDown(divider, { key: 'ArrowLeft' }); });
      expect(capturedCtx.paneWidth).toBeLessThan(widthBefore);
    });
  });

  describe('#1910 - inner row resize divider', () => {
    it('row divider has tabIndex=0', () => {
      render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
      fireEvent.click(screen.getByText('add-a'));
      fireEvent.click(screen.getByText('add-b'));
      const rowDividers = screen.getAllByRole('separator', { name: /resize between window/i });
      expect(rowDividers.length).toBeGreaterThan(0);
      rowDividers.forEach((d) => expect(d).toHaveAttribute('tabindex', '0'));
    });

    it('ArrowDown on row divider increases aria-valuenow (ratio goes up)', () => {
      render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
      fireEvent.click(screen.getByText('add-a'));
      fireEvent.click(screen.getByText('add-b'));
      const rowDivider = screen.getAllByRole('separator', { name: /resize between window/i })[0];
      // Starts at ratio 0.5 -> aria-valuenow=50
      const valueBefore = parseInt(rowDivider.getAttribute('aria-valuenow'), 10);
      act(() => { fireEvent.keyDown(rowDivider, { key: 'ArrowDown' }); });
      const valueAfter = parseInt(rowDivider.getAttribute('aria-valuenow'), 10);
      // ArrowDown increases ratio by 0.05 -> aria-valuenow goes from 50 to 55
      expect(valueAfter).toBeGreaterThan(valueBefore);
    });

    it('ArrowUp on row divider decreases aria-valuenow (ratio goes down)', () => {
      render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
      fireEvent.click(screen.getByText('add-a'));
      fireEvent.click(screen.getByText('add-b'));
      const rowDivider = screen.getAllByRole('separator', { name: /resize between window/i })[0];
      const valueBefore = parseInt(rowDivider.getAttribute('aria-valuenow'), 10);
      act(() => { fireEvent.keyDown(rowDivider, { key: 'ArrowUp' }); });
      const valueAfter = parseInt(rowDivider.getAttribute('aria-valuenow'), 10);
      // ArrowUp decreases ratio by 0.05 -> aria-valuenow goes from 50 to 45
      expect(valueAfter).toBeLessThan(valueBefore);
    });
  });
});
