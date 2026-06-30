import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ChartKeyboardControls from './ChartKeyboardControls.jsx';

describe('ChartKeyboardControls', () => {
  it('renders nothing when there are no items', () => {
    const { container } = render(<ChartKeyboardControls label="x" items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders one focusable button per data point with its label', () => {
    const items = [
      { key: 'a', text: 'Run A: 6.6', onActivate: vi.fn() },
      { key: 'b', text: 'Run B: 7.2', onActivate: vi.fn() },
    ];
    render(<ChartKeyboardControls label="Score history" items={items} />);
    const group = screen.getByRole('list', { name: 'Score history' });
    expect(group).toBeInTheDocument();
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toHaveTextContent('Run A: 6.6');
  });

  it('activates on click — reaching the same handler a mouse click does', () => {
    const onActivate = vi.fn();
    render(<ChartKeyboardControls label="x" items={[{ key: 'a', text: 'Run A', onActivate }]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Run A' }));
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it('activates on Enter and Space', () => {
    const onActivate = vi.fn();
    render(<ChartKeyboardControls label="x" items={[{ key: 'a', text: 'Run A', onActivate }]} />);
    const btn = screen.getByRole('button', { name: 'Run A' });
    fireEvent.keyDown(btn, { key: 'Enter' });
    fireEvent.keyDown(btn, { key: ' ' });
    expect(onActivate).toHaveBeenCalledTimes(2);
  });
});
