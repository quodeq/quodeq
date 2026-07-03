import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import GradeFormulaCurveFigure from './GradeFormulaCurveFigure.jsx';
import ScoreGroupingFigure from './ScoreGroupingFigure.jsx';

// Presentational smoke tests: figures must render, be decorative
// (HelpFigure supplies the accessible description via its caption),
// and contain no hardcoded hex colors so they theme correctly.

describe('help figures', () => {
  it('GradeFormulaCurveFigure renders an svg and three severity chips', () => {
    const { container } = render(<GradeFormulaCurveFigure />);
    expect(container.querySelector('svg')).not.toBeNull();
    expect(container.querySelectorAll('.severity-tag').length).toBe(3);
  });

  it('ScoreGroupingFigure renders period options and bars', () => {
    const { container, getByText } = render(<ScoreGroupingFigure />);
    expect(getByText(/Day/)).toBeTruthy();
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('figures contain no hardcoded colors in markup', () => {
    // Guards the attribute channel (fill/stroke); jsdom normalizes inline-style
    // hex to rgb(), so style-object colors would not be caught here.
    for (const Fig of [GradeFormulaCurveFigure, ScoreGroupingFigure]) {
      const { container } = render(<Fig />);
      expect(container.innerHTML).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgb\(/);
    }
  });

  it('figures introduce no focusable elements', () => {
    for (const Fig of [GradeFormulaCurveFigure, ScoreGroupingFigure]) {
      const { container } = render(<Fig />);
      expect(container.querySelector('[tabindex]')).toBeNull();
    }
  });
});
