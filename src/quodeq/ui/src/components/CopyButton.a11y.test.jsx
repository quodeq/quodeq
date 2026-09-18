import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import CopyButton from './CopyButton.jsx';

describe('CopyButton accessible name fallback', () => {
  it('falls back to a default aria-label when called with an icon but no label or aria-label', () => {
    render(<CopyButton icon={<svg />} onClick={() => {}} />);
    expect(screen.getByRole('button', { name: 'Copy to clipboard' })).toBeInTheDocument();
  });
});
