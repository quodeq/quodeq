import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import CompareRadar from './CompareRadar.jsx';

const axes = [
  { label: 'Integrity', value: 7.5 },
  { label: 'Confidentiality', value: 6.2 },
  { label: 'Authenticity', value: 8 },
];
const series = [{ values: [7.5, 6.2, 8], variant: 'lead' }];

const renderRadar = () => render(<CompareRadar axes={axes} series={series} />);

describe('CompareRadar accessibility', () => {
  it('#6409 names the radar image', () => {
    renderRadar();
    expect(screen.getByRole('img', { name: 'Radar chart of dimension scores' })).toBeInTheDocument();
  });

  it('#6410 leaves the axis names and scores in the accessible tree', () => {
    const { container } = renderRadar();
    expect(container.querySelector('.compare-radar__labels')).not.toHaveAttribute('aria-hidden');
    expect(screen.getByText('7.5')).toBeVisible();
    expect(screen.getByText('Integrity')).toBeVisible();
  });
});
