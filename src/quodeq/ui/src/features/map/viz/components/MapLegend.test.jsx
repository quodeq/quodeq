import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import MapLegend, { VizTooltipAnchor } from './MapLegend.jsx';
import { LEGEND_ITEMS } from '../core/galaxyCore.js';

describe('MapLegend', () => {
  it('renders one entry per LEGEND_ITEMS label, in order', () => {
    const { container } = render(<MapLegend />);
    expect(container.textContent.trim()).toBe(LEGEND_ITEMS.map((item) => item.label).join(''));
  });
});

describe('VizTooltipAnchor', () => {
  it('attaches the passed ref to a hidden fixed-position div', () => {
    const tooltipRef = { current: null };
    const { container } = render(<VizTooltipAnchor tooltipRef={tooltipRef} />);
    const el = container.firstChild;
    expect(tooltipRef.current).toBe(el);
    expect(el).toHaveStyle({ display: 'none', position: 'fixed' });
  });
});
