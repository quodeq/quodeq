import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import GradeFormulaCurveFigure from './GradeFormulaCurveFigure.jsx';

// #6043 - the curve svg had no accessible name/description for its two
// distinct curves (base score curve vs. violation ceiling); the only
// explanation lived in a source comment invisible to users.
describe('GradeFormulaCurveFigure svg a11y', () => {
  it('exposes the svg as an image with an accessible name', () => {
    const { container } = render(<GradeFormulaCurveFigure />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('role', 'img');
    expect(svg).toHaveAttribute(
      'aria-label',
      'Grade curve: the solid line is the base score curve, the dashed line is the violation ceiling',
    );
  });
});
