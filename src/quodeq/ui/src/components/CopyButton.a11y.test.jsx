import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import CopyButton from './CopyButton.jsx';

describe('CopyButton accessible name fallback', () => {
  it('falls back to a default aria-label when called with an icon but no label or aria-label', () => {
    render(<CopyButton icon={<svg />} onClick={() => {}} />);
    expect(screen.getByRole('button', { name: 'Copy to clipboard' })).toBeInTheDocument();
  });

  it('lets the name follow the content when there is a label', () => {
    render(<CopyButton label="Copy" onClick={vi.fn()} />);
    const btn = screen.getByRole('button', { name: 'Copy' });
    fireEvent.click(btn);
    expect(screen.getByRole('button', { name: 'Copied!' })).toBe(btn);
  });
});
