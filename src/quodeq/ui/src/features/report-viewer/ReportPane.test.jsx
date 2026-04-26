import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ReportPane } from './ReportPane.jsx';
import { ReportViewerProvider } from './ReportViewerProvider.jsx';
import { useReportViewer } from './ReportViewerContext.jsx';

function Opener({ title = 'My Report', markdown = '# Body' } = {}) {
  const { openReport } = useReportViewer();
  return <button onClick={() => openReport({ title, markdown })}>open</button>;
}

function harness(props) {
  return render(
    <ReportViewerProvider>
      <Opener {...props} />
      <ReportPane />
    </ReportViewerProvider>
  );
}

describe('ReportPane', () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it('renders nothing while closed', () => {
    harness();
    expect(screen.queryByRole('complementary', { name: /report/i })).toBeNull();
  });

  it('renders the title immediately and the markdown body once the slide finishes', async () => {
    harness({ title: 'Quality Report', markdown: '# Hello' });
    fireEvent.click(screen.getByText('open'));
    expect(screen.getByText('Quality Report')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Hello' })).toBeInTheDocument();
    });
  });

  it('Copy button writes the current markdown to the clipboard', () => {
    harness({ markdown: '# Body' });
    fireEvent.click(screen.getByText('open'));
    fireEvent.click(screen.getByRole('button', { name: /copy/i }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('# Body');
  });

  it('Close button closes the pane', () => {
    harness();
    fireEvent.click(screen.getByText('open'));
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByRole('complementary', { name: /report/i })).toBeNull();
  });

  it('renders the empty-state message for empty markdown after the slide finishes', async () => {
    harness({ markdown: '' });
    fireEvent.click(screen.getByText('open'));
    await waitFor(() => {
      expect(screen.getByText(/no content/i)).toBeInTheDocument();
    });
  });
});
