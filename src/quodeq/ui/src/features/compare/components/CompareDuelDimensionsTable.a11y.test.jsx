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
    expect(screen.getAllByLabelText(/^Alpha: /)).toHaveLength(dimensions.length);
    expect(screen.getByLabelText('Alpha: 7.0')).toHaveTextContent('7.0');
    expect(screen.getByLabelText('Beta: 5.5')).toHaveTextContent('5.5');
  });

  it('keeps the two sides of a row apart even when the scores are equal', () => {
    renderTable();
    expect(screen.getByLabelText('Alpha: 6.0')).toBeInTheDocument();
    expect(screen.getByLabelText('Beta: 6.0')).toBeInTheDocument();
  });
});
