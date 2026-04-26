import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ReportSplitButton } from './ReportSplitButton.jsx';
import { ReportViewerProvider } from './ReportViewerProvider.jsx';
import { useReportViewer } from './ReportViewerContext.jsx';

function StateProbe() {
  const { current, isOpen } = useReportViewer();
  return <div data-testid="state">{isOpen ? `open:${current?.title}` : 'closed'}</div>;
}

function harness({ buildMarkdown = () => '# Hello' } = {}) {
  return render(
    <ReportViewerProvider>
      <StateProbe />
      <ReportSplitButton title="Quality Report" buildMarkdown={buildMarkdown} label="Report" />
    </ReportViewerProvider>
  );
}

describe('ReportSplitButton', () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it('main click opens the pane with the resolved markdown', () => {
    const build = vi.fn(() => '# Body');
    harness({ buildMarkdown: build });
    fireEvent.click(screen.getByRole('button', { name: 'Report' }));
    expect(build).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('state')).toHaveTextContent('open:Quality Report');
  });

  it('chevron toggles the menu', () => {
    harness();
    expect(screen.queryByRole('menu')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /more report actions/i }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });

  it('Copy as Markdown writes to clipboard without opening the pane', () => {
    harness({ buildMarkdown: () => '# Body' });
    fireEvent.click(screen.getByRole('button', { name: /more report actions/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /copy as markdown/i }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('# Body');
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('Escape closes the menu', () => {
    harness();
    fireEvent.click(screen.getByRole('button', { name: /more report actions/i }));
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
  });
});
