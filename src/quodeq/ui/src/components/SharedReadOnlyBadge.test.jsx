import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import SharedReadOnlyBadge from './SharedReadOnlyBadge.jsx';

describe('SharedReadOnlyBadge', () => {
  it('renders the exact "shared · read-only" chip text', () => {
    render(<SharedReadOnlyBadge />);
    expect(screen.getByText('shared · read-only')).toBeInTheDocument();
  });

  it('uses a middle dot, not an em-dash', () => {
    render(<SharedReadOnlyBadge />);
    const text = screen.getByText('shared · read-only').textContent;
    expect(text).not.toMatch(/—|--/);
    expect(text).toContain('·'); // ·
  });

  it('shows the publisher sub line when publishedBy is provided', () => {
    render(<SharedReadOnlyBadge publishedBy="alice" />);
    expect(screen.getByText('published by alice')).toBeInTheDocument();
  });

  it('omits the publisher sub line when publishedBy is not available', () => {
    render(<SharedReadOnlyBadge />);
    expect(screen.queryByText(/published by/)).toBeNull();
  });
});
