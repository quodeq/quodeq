import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ServerStatusPill from './ServerStatusPill.jsx';

describe('ServerStatusPill', () => {
  it('renders online status with address', () => {
    render(<ServerStatusPill status="online" address="localhost:7863" />);
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('localhost:7863')).toBeInTheDocument();
  });

  it('renders offline status with the supplied offline message', () => {
    render(
      <ServerStatusPill
        status="offline"
        offlineMessage={<span>Run something</span>}
      />
    );
    expect(screen.getByText('Run something')).toBeInTheDocument();
  });

  it('renders the ConsoleButton segment only when online and onToggleConsole is provided', () => {
    const onToggle = vi.fn();
    const { rerender, container } = render(
      <ServerStatusPill status="online" address="x" onToggleConsole={onToggle} />
    );
    expect(container.querySelector('.console-button')).not.toBeNull();
    expect(container.querySelector('.server-status-pill__divider')).not.toBeNull();

    rerender(<ServerStatusPill status="offline" onToggleConsole={onToggle} />);
    expect(container.querySelector('.console-button')).toBeNull();
    expect(container.querySelector('.server-status-pill__divider')).toBeNull();

    rerender(<ServerStatusPill status="online" address="x" />);
    expect(container.querySelector('.console-button')).toBeNull();
  });

  it('calls onToggleConsole when the inner button is clicked', () => {
    const onToggle = vi.fn();
    render(
      <ServerStatusPill
        status="online"
        address="x"
        onToggleConsole={onToggle}
        consoleOpen={false}
      />
    );
    fireEvent.click(screen.getByLabelText('Show console'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('passes consoleOpen and showDot to the inner ConsoleButton', () => {
    const { container, rerender } = render(
      <ServerStatusPill status="online" address="x" onToggleConsole={() => {}} consoleOpen showDot />
    );
    expect(screen.getByLabelText('Hide console')).toBeInTheDocument();
    expect(container.querySelector('.console-button__dot')).not.toBeNull();
    rerender(
      <ServerStatusPill status="online" address="x" onToggleConsole={() => {}} consoleOpen={false} />
    );
    expect(screen.getByLabelText('Show console')).toBeInTheDocument();
    expect(container.querySelector('.console-button__dot')).toBeNull();
  });
});
