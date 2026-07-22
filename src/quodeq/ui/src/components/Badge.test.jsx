import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import Badge from './Badge.jsx';

describe('Badge', () => {
  it('renders children with tone and variant classes and a tooltip', () => {
    render(<Badge tone="info" variant="tag" title="tip">remote · read-only</Badge>);
    const el = screen.getByText('remote · read-only');
    expect(el).toHaveClass('badge', 'badge--tag', 'badge--info');
    expect(el).toHaveAttribute('title', 'tip');
  });
  it('defaults to a neutral tag', () => {
    render(<Badge>x</Badge>);
    expect(screen.getByText('x')).toHaveClass('badge', 'badge--tag', 'badge--neutral');
  });
  it('falls back to neutral on an unknown tone', () => {
    render(<Badge tone="sparkly">x</Badge>);
    expect(screen.getByText('x')).toHaveClass('badge--neutral');
  });
  it('appends a caller className for layout-only tweaks', () => {
    render(<Badge className="drawer-model-chip">x</Badge>);
    expect(screen.getByText('x')).toHaveClass('badge', 'drawer-model-chip');
  });
});
