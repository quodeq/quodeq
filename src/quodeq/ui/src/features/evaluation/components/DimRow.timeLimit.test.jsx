import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import DimRow from './DimRow.jsx';

const dim = (exitReason) => ({
  id: 'usability', state: 'done', exitReason, files: { taken: 0, total: 19 }, violations: 0, compliance: 0,
});

describe('DimRow when a dimension ran out of time', () => {
  it('shows how far it got in the partial colour instead of a full green bar', () => {
    const { container } = render(<DimRow dim={dim('time_limit')} />);
    const fill = container.querySelector('.scan-progress__bar-fill');
    expect(fill.className).toContain('scan-progress__bar-fill--partial');
    expect(fill.style.width).toBe('0%');
    expect(container.querySelector('.scan-progress__dim-dot--partial')).not.toBeNull();
  });

  it('keeps a finished dimension full and green', () => {
    const { container } = render(<DimRow dim={dim('done')} />);
    const fill = container.querySelector('.scan-progress__bar-fill');
    expect(fill.className).toContain('scan-progress__bar-fill--done');
    expect(fill.style.width).toBe('100%');
  });
});
