import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePane } from './SidePane.jsx';
import { SidePaneProvider } from './SidePaneProvider.jsx';
import { useSidePane } from './SidePaneContext.jsx';

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

function spec(id, title = id) {
  return { id, type: 'report', title, render: () => <p>{`body:${id}`}</p> };
}

function Adder() {
  const { addWindow } = useSidePane();
  return (
    <div>
      <button onClick={() => addWindow(spec('alpha', 'Alpha'))}>add-a</button>
      <button onClick={() => addWindow(spec('beta', 'Beta'))}>add-b</button>
      <button onClick={() => addWindow(spec('gamma', 'Gamma'))}>add-c</button>
    </div>
  );
}

describe('SidePane', () => {
  it('renders nothing when no windows', () => {
    render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
    expect(screen.queryByRole('complementary', { name: /side pane/i })).toBeNull();
  });

  it('renders one window with its title and body when one is added', () => {
    render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    expect(screen.getByRole('complementary', { name: /side pane/i })).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('body:alpha')).toBeInTheDocument();
  });

  it('renders multiple windows in registration order with a horizontal resizer between them', () => {
    render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    fireEvent.click(screen.getByText('add-c'));
    const titles = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(titles).toEqual(['Alpha', 'Beta', 'Gamma']);
    const resizers = screen.getAllByRole('separator', { name: /resize between window/i });
    expect(resizers).toHaveLength(2);
  });

  it('clicking a window close button removes it from the dock', () => {
    render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    fireEvent.click(screen.getByText('add-b'));
    const closes = screen.getAllByRole('button', { name: /close window/i });
    expect(closes).toHaveLength(2);
    fireEvent.click(closes[0]);
    expect(screen.queryByText('Alpha')).toBeNull();
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  it('renders an outer left-edge resize gutter (vertical separator)', () => {
    render(<SidePaneProvider><Adder /><SidePane /></SidePaneProvider>);
    fireEvent.click(screen.getByText('add-a'));
    expect(screen.getByRole('separator', { name: /resize side pane/i })).toBeInTheDocument();
  });
});
