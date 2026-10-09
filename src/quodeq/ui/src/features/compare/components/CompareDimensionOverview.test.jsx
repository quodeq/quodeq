import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CompareDimensionKpis from './CompareDimensionKpis.jsx';
import ComparePrincipleHealth from './ComparePrincipleHealth.jsx';
import { dimensionRows } from '../compareDimensionOverview.js';

const project = (id, files) => ({ id, name: id, totalFiles: files, analyzedFiles: null });
const VIEW = {
  key: 'flexibility', label: 'flexibility', avg: 7.5, delta: 0.4, spread: 2,
  standings: [
    { row: project('a', 900), score: 8.5, delta: 0.6, violations: 9, compliance: 91, severity: { critical: 9 },
      principles: [{ key: 'inst', label: 'installability', score: 9 }, { key: 'adap', label: 'adaptability', score: 8 }] },
    { row: project('b', 100), score: 6.5, delta: null, violations: 11, compliance: 89, severity: { critical: 1 },
      principles: [{ key: 'adap', label: 'adaptability', score: 5 }] },
  ],
  principles: [
    { key: 'adap', label: 'adaptability', avg: 6.5, lead: { id: 'a', name: 'a', score: 8 }, perProject: [{ id: 'a', name: 'a', score: 8 }, { id: 'b', name: 'b', score: 5 }] },
    { key: 'inst', label: 'installability', avg: 9, lead: { id: 'a', name: 'a', score: 9 }, perProject: [{ id: 'a', name: 'a', score: 9 }] },
  ],
};
VIEW.lead = VIEW.standings[0];
VIEW.trail = VIEW.standings[1];

describe('CompareDimensionKpis', () => {
  it('states below good and coverage against the whole scope', () => {
    render(<CompareDimensionKpis view={VIEW} rows={dimensionRows(VIEW)} scopeCount={5} />);
    const strip = screen.getByRole('region', { name: 'flexibility summary' });
    expect(strip).toHaveTextContent('1/2');
    expect(strip).toHaveTextContent('2/5');
    expect(strip).toHaveTextContent('projects with flexibility scored');
  });
});

describe('ComparePrincipleHealth', () => {
  it('ranks principles weakest first with coverage, and a row opens the trailer’s principle', async () => {
    const onOpenPrinciple = vi.fn();
    render(<ComparePrincipleHealth view={VIEW} onOpenPrinciple={onOpenPrinciple} />);
    const panel = screen.getByRole('region', { name: 'Principle health in flexibility' });
    const rows = within(panel).getAllByRole('button');
    expect(rows[0]).toHaveTextContent(/^adaptability/);
    expect(rows[0]).toHaveTextContent('2 of 2');
    expect(rows[1]).toHaveTextContent('1 of 2');
    await userEvent.click(rows[0]);
    expect(onOpenPrinciple).toHaveBeenCalledWith({ id: 'b', name: 'b', score: 5 });
  });
});
