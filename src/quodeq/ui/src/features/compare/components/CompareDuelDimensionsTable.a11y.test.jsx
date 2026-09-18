import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import CompareDuelDimensionsTable from './CompareDuelDimensionsTable.jsx';

const dimensions = [
  { key: 'security', label: 'Security', a: 7, b: 5.5, gap: 1.5 },
  { key: 'usability', label: 'Usability', a: 6, b: 6, gap: 0 },
];

const renderTable = () => render(
  <CompareDuelDimensionsTable dimensions={dimensions} aName="Alpha" bName="Beta" />,
);

describe('CompareDuelDimensionsTable accessibility (#6678)', () => {
  it('names each score with the project it belongs to', () => {
    renderTable();
    expect(screen.getAllByText(/^Alpha: /)).toHaveLength(dimensions.length);
    expect(screen.getByText('Alpha: 7.0')).toBeInTheDocument();
    expect(screen.getByText('Beta: 5.5')).toBeInTheDocument();
  });

  it('keeps the two sides of a row apart even when the scores are equal', () => {
    renderTable();
    expect(screen.getByText('Alpha: 6.0')).toBeInTheDocument();
    expect(screen.getByText('Beta: 6.0')).toBeInTheDocument();
  });

  it('carries the name as visually hidden text, not aria-label on a bare span', () => {
    const { container } = renderTable();
    // aria-label is prohibited on a role-less span (ARIA 1.2), so the name
    // has to be real text: the digits are hidden, the sr-only span is read.
    expect(container.querySelectorAll('.compare-duel-dims__score[aria-label]')).toHaveLength(0);
    expect(container.querySelectorAll('.compare-duel-dims__score .sr-only')).toHaveLength(4);
    expect(screen.getByText('Alpha: 7.0')).toHaveClass('sr-only');
    expect(screen.getByText('7.0')).toHaveAttribute('aria-hidden', 'true');
  });
});
