import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RadarPanelShell from './RadarPanelShell.jsx';
import CompareRadarPanel from './CompareRadarPanel.jsx';

function radarView(count) {
  return {
    principles: Array.from({ length: count }, (_, i) => ({ principle: `p${i}` })),
  };
}

const ACTIVE = { row: { id: 'alpha', name: 'Alpha' } };
const axesFor = (count) => Array.from({ length: count }, (_, i) => ({ label: `p${i}`, value: 5 }));
const seriesFor = (count) => [
  { values: Array(count).fill(5), variant: 'average' },
  { values: Array(count).fill(6), variant: 'project' },
];

describe('RadarPanelShell', () => {
  it('names the section and renders the heading row', () => {
    render(
      <RadarPanelShell ariaLabel="Shape" header="SHAPE" note="0-10" items={[1, 2, 3]}>
        <p>body</p>
      </RadarPanelShell>
    );
    const section = screen.getByLabelText('Shape');
    expect(section.tagName).toBe('SECTION');
    expect(section).toHaveClass('compare-panel');
    expect(section.querySelector('.compare-panel__note')).toHaveTextContent('0-10');
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  it('falls back to the too-few message below the axis minimum', () => {
    render(
      <RadarPanelShell ariaLabel="Shape" header="SHAPE" note="0-10" items={[1, 2]}>
        <p>body</p>
      </RadarPanelShell>
    );
    expect(screen.queryByText('body')).toBeNull();
    expect(document.querySelector('.compare-panel__fallback')).toBeInTheDocument();
  });

  it('honours an explicit minItems', () => {
    render(
      <RadarPanelShell ariaLabel="Shape" header="SHAPE" note="n" items={[1, 2]} minItems={2}>
        <p>body</p>
      </RadarPanelShell>
    );
    expect(screen.getByText('body')).toBeInTheDocument();
  });
});

describe('compare radar panels', () => {
  it('CompareRadarPanel draws the radar with the active project and the average in the legend', () => {
    const { container } = render(
      <CompareRadarPanel view={radarView(3)} axes={axesFor(3)} series={seriesFor(3)} active={ACTIVE} />
    );
    expect(container.querySelector('section.compare-panel')).toHaveAttribute('aria-label');
    expect(screen.getByRole('img', { name: /radar chart/i })).toBeInTheDocument();
    expect(container.querySelectorAll('.compare-radar__legendItem')).toHaveLength(2);
    expect(screen.getByText('Alpha')).toHaveClass('compare-radar__legendItem--project');
    expect(container.querySelectorAll('.compare-radar__poly--project')).toHaveLength(1);
    expect(container.querySelectorAll('.compare-radar__poly--average')).toHaveLength(1);
  });

  it('CompareRadarPanel lists only the average without an active project', () => {
    const { container } = render(
      <CompareRadarPanel view={radarView(3)} axes={axesFor(3)} series={seriesFor(3).slice(0, 1)} />
    );
    expect(container.querySelectorAll('.compare-radar__legendItem')).toHaveLength(1);
  });

  it('CompareRadarPanel shows the fallback with fewer than three principles', () => {
    const { container } = render(
      <CompareRadarPanel view={radarView(2)} axes={axesFor(2)} series={seriesFor(2)} />
    );
    expect(container.querySelector('.compare-panel__fallback')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /radar chart/i })).toBeNull();
  });
});
