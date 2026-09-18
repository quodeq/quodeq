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
    expect(screen.getByLabelText('Alpha: 8.0')).toHaveTextContent('8.0');
    expect(screen.getByLabelText('Beta: 4.5')).toHaveTextContent('4.5');
    // The legend swatches stay decorative: they carry no text of their own.
    const swatches = container.querySelectorAll('.compare-duel-principles__side');
    expect(swatches).toHaveLength(2);
    swatches.forEach((s) => expect(s).toHaveAttribute('aria-hidden', 'true'));
  });

  it('#6371 names each per-principle row score after its side', () => {
    renderPrinciples();
    expect(screen.getByLabelText('Alpha: 7.0')).toHaveTextContent('7.0');
    expect(screen.getByLabelText('Beta: 5.5')).toHaveTextContent('5.5');
  });

  it('#6370/#6371 keeps heading and row scores separately labelled', () => {
    renderPrinciples();
    expect(screen.getAllByLabelText(/^Alpha: /)).toHaveLength(2);
    expect(screen.getAllByLabelText(/^Beta: /)).toHaveLength(2);
  });
});
