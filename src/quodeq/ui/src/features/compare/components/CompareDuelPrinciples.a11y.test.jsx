import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import CompareDuelPrinciples from './CompareDuelPrinciples.jsx';

const principles = [
  { key: 'security', label: 'Security', items: [{ key: 'integrity', label: 'Integrity', a: 7, b: 5.5, gap: 1.5 }] },
];
const dimensions = [{ key: 'security', label: 'Security', a: 8, b: 4.5, gap: 3.5, shared: true }];

const renderPrinciples = () => render(
  <CompareDuelPrinciples
    principles={principles}
    dimensions={dimensions}
    aName="Alpha"
    bName="Beta"
  />,
);

describe('CompareDuelPrinciples accessibility', () => {
  it('#6370 names the group-heading dimension scores after their side', () => {
    const { container } = renderPrinciples();
    expect(screen.getByText('Alpha: 8.0')).toBeInTheDocument();
    expect(screen.getByText('Beta: 4.5')).toBeInTheDocument();
    // The legend swatches stay decorative: they carry no text of their own.
    const swatches = container.querySelectorAll('.compare-duel-principles__side');
    expect(swatches).toHaveLength(2);
    swatches.forEach((s) => expect(s).toHaveAttribute('aria-hidden', 'true'));
  });

  it('#6371 names each per-principle row score after its side', () => {
    renderPrinciples();
    expect(screen.getByText('Alpha: 7.0')).toBeInTheDocument();
    expect(screen.getByText('Beta: 5.5')).toBeInTheDocument();
  });

  it('#6370/#6371 keeps heading and row scores separately labelled', () => {
    renderPrinciples();
    expect(screen.getAllByText(/^Alpha: /)).toHaveLength(2);
    expect(screen.getAllByText(/^Beta: /)).toHaveLength(2);
  });

  it('#6370/#6371 carries the name as visually hidden text, not aria-label', () => {
    const { container } = renderPrinciples();
    // aria-label is prohibited on a role-less span (ARIA 1.2).
    expect(container.querySelectorAll('span[aria-label]')).toHaveLength(0);
    expect(screen.getByText('Alpha: 7.0')).toHaveClass('sr-only');
    expect(screen.getByText('7.0')).toHaveAttribute('aria-hidden', 'true');
  });
});
