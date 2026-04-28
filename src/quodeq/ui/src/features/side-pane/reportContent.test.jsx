import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ReportContent } from './reportContent.jsx';

describe('ReportContent', () => {
  it('renders headings inside the report-pane-md scope', () => {
    const { container } = render(<ReportContent markdown={"# Title\n\n## Subtitle"} />);
    expect(container.querySelector('.report-pane-md h1')).toHaveTextContent('Title');
    expect(container.querySelector('.report-pane-md h2')).toHaveTextContent('Subtitle');
  });

  it('renders inline code and code blocks', () => {
    const md = "Some `inline` code.\n\n```python\nprint('hi')\n```";
    const { container } = render(<ReportContent markdown={md} />);
    const inline = container.querySelector('p code');
    expect(inline).not.toBeNull();
    expect(inline).toHaveTextContent('inline');
    expect(container.querySelector('pre > code')).toHaveTextContent("print('hi')");
  });

  it('renders GFM tables', () => {
    const md = "| a | b |\n| - | - |\n| 1 | 2 |";
    const { container } = render(<ReportContent markdown={md} />);
    expect(container.querySelectorAll('th').length).toBe(2);
    expect(container.querySelectorAll('td').length).toBe(2);
  });

  it('opens links in a new tab with safe rel attributes', () => {
    const { container } = render(<ReportContent markdown="[a](https://example.com)" />);
    const a = container.querySelector('a');
    expect(a).toHaveAttribute('target', '_blank');
    expect(a.getAttribute('rel') || '').toMatch(/noopener/);
  });

  it('renders empty markdown as the empty-state message', () => {
    const { container } = render(<ReportContent markdown="" />);
    expect(container.textContent).toMatch(/no content/i);
  });
});
