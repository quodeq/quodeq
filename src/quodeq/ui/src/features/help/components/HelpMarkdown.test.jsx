import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HelpMarkdown from './HelpMarkdown.jsx';

describe('HelpMarkdown', () => {
  it('renders a Tip callout from a bold-titled blockquote', () => {
    const { container } = render(
      <HelpMarkdown source={'> **Heads up**\n>\n> Body text here.'} />,
    );
    expect(container.querySelector('.help-tip__title').textContent).toBe('Heads up');
    expect(container.querySelector('.help-tip__body').textContent).toContain('Body text here.');
  });

  it('renders a KeyTable from a GFM table, keyed and valued by column', () => {
    const { container } = render(
      <HelpMarkdown source={'| Key | Value |\n| --- | --- |\n| LOCAL | only here |'} />,
    );
    expect(container.querySelector('.help-keytable__k').textContent).toBe('LOCAL');
    expect(container.querySelector('.help-keytable__v').textContent).toBe('only here');
  });

  it('resolves a severity badge label from the catalog, not the markdown', () => {
    const { container } = render(<HelpMarkdown source={'Text `tag:critical` more.'} />);
    const badge = container.querySelector('.severity-tag.critical');
    expect(badge.textContent).toBe('CRITICAL');
  });

  // Registry lookups previously used a plain truthy check, so an inherited
  // Object.prototype key resolved to a function and was rendered as a
  // component -- crashing the page the fallback exists to protect.
  for (const inherited of ['toString', 'constructor', 'valueOf', 'hasOwnProperty']) {
    it(`skips a figure named "${inherited}" instead of crashing`, () => {
      const src = ['```figure', `component: ${inherited}`, 'caption: x', '```'].join('\n');
      expect(() => render(<HelpMarkdown source={src} />)).not.toThrow();
    });

    it(`skips an icon named "${inherited}" instead of crashing`, () => {
      expect(() => render(<HelpMarkdown source={`a \`icon:${inherited}\` b`} />)).not.toThrow();
    });
  }

  it('still renders a known figure', () => {
    const src = ['```figure', 'component: ScoreGroupingFigure', 'caption: cap', '```'].join('\n');
    const { container } = render(<HelpMarkdown source={src} />);
    expect(container.querySelector('.sg-figure')).toBeTruthy();
  });

  // #6043 fix round 1 - HelpFigure wraps illustration children in
  // aria-hidden="true" by default, which suppressed GradeFormulaCurveFigure's
  // role="img"/aria-label from ever reaching a screen reader on the real Help
  // page. The registry now marks it informative so HelpFigure skips hiding it.
  it('keeps the grade-curve figure in the accessibility tree', () => {
    const src = ['```figure', 'component: GradeFormulaCurveFigure', 'caption: cap', '```'].join('\n');
    render(<HelpMarkdown source={src} />);
    expect(screen.getByRole('img', { name: /grade curve/i })).toBeInTheDocument();
  });

  it('still hides the decorative score-grouping figure from the accessibility tree', () => {
    const src = ['```figure', 'component: ScoreGroupingFigure', 'caption: cap', '```'].join('\n');
    render(<HelpMarkdown source={src} />);
    expect(screen.queryByRole('img')).toBeNull();
  });
});
