import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ConsoleButton from './ConsoleButton.jsx';

describe('ConsoleButton', () => {
  it('shows "Show console" aria-label when closed', () => {
    render(<ConsoleButton open={false} onToggle={() => {}} />);
    expect(screen.getByLabelText('Show console')).toBeInTheDocument();
  });

  it('shows "Hide console" aria-label when open', () => {
    render(<ConsoleButton open onToggle={() => {}} />);
    expect(screen.getByLabelText('Hide console')).toBeInTheDocument();
  });

  it('calls onToggle on click and stops event propagation', () => {
    const onToggle = vi.fn();
    const onParentClick = vi.fn();
    render(
      <div onClick={onParentClick}>
        <ConsoleButton open={false} onToggle={onToggle} />
      </div>
    );
    fireEvent.click(screen.getByLabelText('Show console'));
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onParentClick).not.toHaveBeenCalled();
  });

  it('renders the dot when showDot=true', () => {
    const { container } = render(<ConsoleButton open={false} onToggle={() => {}} showDot />);
    expect(container.querySelector('.console-button__dot')).not.toBeNull();
  });

  it('does not render the dot when showDot=false (default)', () => {
    const { container } = render(<ConsoleButton open={false} onToggle={() => {}} />);
    expect(container.querySelector('.console-button__dot')).toBeNull();
  });
});
