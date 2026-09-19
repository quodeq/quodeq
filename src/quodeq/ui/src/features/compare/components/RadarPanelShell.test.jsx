import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RadarPanelShell from './RadarPanelShell.jsx';
import CompareRadarPanel from './CompareRadarPanel.jsx';
import CompareDuelShapePanel from './CompareDuelShapePanel.jsx';

const dim = (label, value) => ({ label, a: value, b: value - 1 });

function radarView(count) {
  return {
    principles: Array.from({ length: count }, (_, i) => ({ principle: `p${i}` })),
    lead: { row: { name: 'Alpha' } },
    trail: { row: { name: 'Beta' } },
  };
}

const axesFor = (count) => Array.from({ length: count }, (_, i) => ({ label: `p${i}`, value: 5 }));
const seriesFor = (count) => [{ values: Array(count).fill(5), variant: 'lead' }];

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
  it('CompareRadarPanel draws the radar and the three legend entries', () => {
    const { container } = render(
      <CompareRadarPanel view={radarView(3)} axes={axesFor(3)} series={seriesFor(3)} />
    );
    expect(container.querySelector('section.compare-panel')).toHaveAttribute('aria-label');
    expect(screen.getByRole('img', { name: /radar chart/i })).toBeInTheDocument();
    expect(container.querySelectorAll('.compare-radar__legendItem')).toHaveLength(3);
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  it('CompareRadarPanel shows the fallback with fewer than three principles', () => {
    const { container } = render(
      <CompareRadarPanel view={radarView(2)} axes={axesFor(2)} series={seriesFor(2)} />
    );
    expect(container.querySelector('.compare-panel__fallback')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /radar chart/i })).toBeNull();
  });

  it('CompareDuelShapePanel draws both projects in the legend', () => {
    const { container } = render(
      <CompareDuelShapePanel
        sharedDims={[dim('One', 8), dim('Two', 7), dim('Three', 6)]}
        a={{ name: 'Proj A' }}
        b={{ name: 'Proj B' }}
      />
    );
    expect(screen.getByRole('img', { name: /radar chart/i })).toBeInTheDocument();
    expect(container.querySelector('.compare-duel__legendItem--a')).toHaveTextContent('Proj A');
    expect(container.querySelector('.compare-duel__legendItem--b')).toHaveTextContent('Proj B');
  });

  it('CompareDuelShapePanel shows the fallback with fewer than three shared dimensions', () => {
    const { container } = render(
      <CompareDuelShapePanel
        sharedDims={[dim('One', 8), dim('Two', 7)]}
        a={{ name: 'Proj A' }}
        b={{ name: 'Proj B' }}
      />
    );
    expect(container.querySelector('.compare-panel__fallback')).toBeInTheDocument();
    expect(container.querySelector('.compare-duel__legendItem--a')).toBeNull();
  });
});
