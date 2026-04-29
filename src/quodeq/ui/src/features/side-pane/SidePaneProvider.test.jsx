import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider } from './SidePaneProvider.jsx';
import { useSidePane } from './SidePaneContext.jsx';

function spec(id, title = id) {
  return { id, type: 'report', title, render: () => <p>{`body:${id}`}</p> };
}

function Probe() {
  const { windows, isOpen, addWindow, removeWindow, toggleWindow, hasWindow, closeAll, MAX_WINDOWS } = useSidePane();
  return (
    <div>
      <div data-testid="state">{isOpen ? `open:${windows.map(w => w.id).join(',')}` : 'closed'}</div>
      <div data-testid="cap">{`cap:${MAX_WINDOWS}`}</div>
      <div data-testid="has-a">{hasWindow('a') ? 'yes' : 'no'}</div>
      <button onClick={() => addWindow(spec('a'))}>add-a</button>
      <button onClick={() => addWindow(spec('b'))}>add-b</button>
      <button onClick={() => addWindow(spec('c'))}>add-c</button>
      <button onClick={() => addWindow(spec('d'))}>add-d</button>
      <button onClick={() => removeWindow('a')}>remove-a</button>
      <button onClick={() => toggleWindow(spec('a'))}>toggle-a</button>
      <button onClick={closeAll}>close-all</button>
    </div>
  );
}

describe('SidePaneProvider', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.style.removeProperty('--side-pane-width');
  });

  it('starts closed with no windows and exposes MAX_WINDOWS=3', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
    expect(screen.getByTestId('cap')).toHaveTextContent('cap:3');
  });

  it('addWindow appends to the bottom of the stack and opens the pane', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:a,b');
  });

  it('addWindow is a no-op when the same id is already present', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-a'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:a');
  });

  it('removeWindow removes by id; pane closes when the last window goes', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    fireEvent.click(screen.getByText('remove-a'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:b');
    fireEvent.click(screen.getByText('remove-a'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:b');
  });

  it('toggleWindow adds when absent and removes when present', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('toggle-a'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:a');
    fireEvent.click(screen.getByText('toggle-a'));
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('addWindow is a no-op when already at MAX_WINDOWS=3', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    fireEvent.click(screen.getByText('add-c'));
    fireEvent.click(screen.getByText('add-d'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:a,b,c');
  });

  it('shows an at-cap toast when addWindow is called past MAX_WINDOWS', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    fireEvent.click(screen.getByText('add-c'));
    expect(screen.queryByRole('status')).toBeNull();
    fireEvent.click(screen.getByText('add-d'));
    expect(screen.getByRole('status')).toHaveTextContent(/3 panels/i);
  });

  it('hasWindow reflects current dock contents', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    expect(screen.getByTestId('has-a')).toHaveTextContent('no');
    fireEvent.click(screen.getByText('add-a'));
    expect(screen.getByTestId('has-a')).toHaveTextContent('yes');
    fireEvent.click(screen.getByText('remove-a'));
    expect(screen.getByTestId('has-a')).toHaveTextContent('no');
  });

  it('closeAll empties the dock', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    fireEvent.click(screen.getByText('close-all'));
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('Escape closes all windows when the pane is open', () => {
    render(<SidePaneProvider><Probe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    act(() => { fireEvent.keyDown(window, { key: 'Escape' }); });
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('useSidePane throws outside the provider', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow();
    consoleSpy.mockRestore();
  });

  it('writes --side-pane-width to the document root when open and 0px when closed', () => {
    function PaneWidthProbe() {
      const { addWindow, closeAll, paneWidth } = useSidePane();
      return (
        <div>
          <div data-testid="pw">{paneWidth}</div>
          <button onClick={() => addWindow(spec('x'))}>add-x</button>
          <button onClick={closeAll}>close-all</button>
        </div>
      );
    }
    render(<SidePaneProvider><PaneWidthProbe /></SidePaneProvider>);
    const initial = screen.getByTestId('pw').textContent;
    expect(Number(initial)).toBeGreaterThan(0);
    fireEvent.click(screen.getByText('add-x'));
    expect(document.documentElement.style.getPropertyValue('--side-pane-width')).toBe(`${initial}px`);
    fireEvent.click(screen.getByText('close-all'));
    expect(document.documentElement.style.getPropertyValue('--side-pane-width')).toBe('0px');
  });

  it('migrates the legacy quodeq.reportPaneWidth localStorage key on first mount', () => {
    localStorage.setItem('quodeq.reportPaneWidth', '777');
    function PWProbe() {
      const { paneWidth } = useSidePane();
      return <div data-testid="pw">{paneWidth}</div>;
    }
    render(<SidePaneProvider><PWProbe /></SidePaneProvider>);
    expect(screen.getByTestId('pw')).toHaveTextContent('777');
    expect(localStorage.getItem('quodeq.sidePaneWidth')).toBe('777');
    expect(localStorage.getItem('quodeq.reportPaneWidth')).toBeNull();
  });

  it('replaceWindow updates the spec in place when id matches', () => {
    function ReplaceProbe() {
      const { addWindow, replaceWindow, windows } = useSidePane();
      return (
        <div>
          <div data-testid="render">{windows[0]?.render?.() ?? 'none'}</div>
          <button onClick={() => addWindow({ id: 'a', type: 't', title: 'A', render: () => 'v1' })}>add</button>
          <button onClick={() => replaceWindow({ id: 'a', type: 't', title: 'A', render: () => 'v2' })}>replace</button>
        </div>
      );
    }
    render(<SidePaneProvider><ReplaceProbe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add'));
    expect(screen.getByTestId('render')).toHaveTextContent('v1');
    fireEvent.click(screen.getByText('replace'));
    expect(screen.getByTestId('render')).toHaveTextContent('v2');
  });

  it('replaceWindow is a no-op when no window with that id exists', () => {
    function NoopProbe() {
      const { replaceWindow, windows } = useSidePane();
      return (
        <div>
          <div data-testid="count">{windows.length}</div>
          <button onClick={() => replaceWindow({ id: 'missing', type: 't', title: 'M', render: () => null })}>r</button>
        </div>
      );
    }
    render(<SidePaneProvider><NoopProbe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('r'));
    expect(screen.getByTestId('count')).toHaveTextContent('0');
  });
});
