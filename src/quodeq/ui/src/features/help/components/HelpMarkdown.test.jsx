import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
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
});
