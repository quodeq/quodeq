import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ScoreGroupingFigure from './ScoreGroupingFigure.jsx';

// #6573 - the mock bar-chart svg was exposed to assistive tech with neither
// aria-hidden nor a role/label, unlike the icon markup in HelpMarkdown.jsx
// that explicitly hides decorative svgs.
describe('ScoreGroupingFigure svg a11y', () => {
  it('hides the decorative svg from assistive tech', () => {
    const { container } = render(<ScoreGroupingFigure />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg).toHaveAttribute('focusable', 'false');
  });
});
