import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import OverviewSkeleton from './OverviewSkeleton.jsx';

// While the server rebuilds a project's scores, the skeleton shows the grade
// it last computed, dimmed, with the updating mark, instead of an empty bar.

describe('OverviewSkeleton', () => {
  it('renders bars and the loading line without a last known grade', () => {
    const { container } = render(<OverviewSkeleton projectName="quodeq" />);
    expect(container.querySelector('.overview-skeleton__last-known')).toBeNull();
    expect(container.querySelector('[data-slot="score"] .overview-skeleton__bar--value')).not.toBeNull();
    expect(container.querySelector('.term-header__sub')).toHaveTextContent('loading quodeq');
  });

  it('shows the last known grade in the score slot and says it is updating', () => {
    const { container } = render(<OverviewSkeleton projectName="quodeq" lastKnown={{ grade: 'B', score: 7.4, files: 12 }} />);
    const value = container.querySelector('[data-slot="score"] .overview-skeleton__last-known');
    expect(value).toHaveTextContent('7.4 B');
    expect(container.querySelector('[data-slot="score"] .overview-skeleton__bar--value')).toBeNull();
    expect(container.querySelector('[data-slot="violations"] .overview-skeleton__bar--value')).not.toBeNull();
    expect(container.querySelector('.term-header__sub')).toHaveTextContent('quodeq: last grade 7.4 B, updating');
  });

  it('treats a summary with neither grade nor score as none', () => {
    const { container } = render(<OverviewSkeleton lastKnown={{ grade: null, score: null, files: 3 }} />);
    expect(container.querySelector('.overview-skeleton__last-known')).toBeNull();
    expect(container.querySelector('.term-header__sub')).toHaveTextContent('loading');
  });
});
