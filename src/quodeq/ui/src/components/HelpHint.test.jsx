import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import HelpHint from './HelpHint.jsx';

describe('HelpHint learn more', () => {
  it('shows a Learn more button in the popover that calls back', () => {
    const onClick = vi.fn();
    render(<HelpHint label="About" learnMore={{ label: 'Learn more', onClick }}>tip</HelpHint>);
    fireEvent.click(screen.getByRole('button', { name: 'About' }));
    fireEvent.click(screen.getByRole('button', { name: 'Learn more' }));
    expect(onClick).toHaveBeenCalled();
  });

  it('has no Learn more button without the prop', () => {
    render(<HelpHint label="About">tip</HelpHint>);
    fireEvent.click(screen.getByRole('button', { name: 'About' }));
    expect(screen.queryByRole('button', { name: 'Learn more' })).toBeNull();
  });
});
