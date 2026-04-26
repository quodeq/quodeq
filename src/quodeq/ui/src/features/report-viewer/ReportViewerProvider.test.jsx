import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ReportViewerProvider } from './ReportViewerProvider.jsx';
import { useReportViewer } from './ReportViewerContext.jsx';

function Probe() {
  const { current, isOpen, openReport, closeReport } = useReportViewer();
  return (
    <div>
      <div data-testid="state">{isOpen ? `open:${current?.title}` : 'closed'}</div>
      <button onClick={() => openReport({ title: 'A', markdown: '# A' })}>open-a</button>
      <button onClick={() => openReport({ title: 'B', markdown: '# B' })}>open-b</button>
      <button onClick={closeReport}>close</button>
    </div>
  );
}

describe('ReportViewerProvider', () => {
  it('starts closed with no current report', () => {
    render(<ReportViewerProvider><Probe /></ReportViewerProvider>);
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('openReport sets current and opens the pane', () => {
    render(<ReportViewerProvider><Probe /></ReportViewerProvider>);
    fireEvent.click(screen.getByText('open-a'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:A');
  });

  it('openReport replaces current in place when already open', () => {
    render(<ReportViewerProvider><Probe /></ReportViewerProvider>);
    fireEvent.click(screen.getByText('open-a'));
    fireEvent.click(screen.getByText('open-b'));
    expect(screen.getByTestId('state')).toHaveTextContent('open:B');
  });

  it('closeReport closes the pane', () => {
    render(<ReportViewerProvider><Probe /></ReportViewerProvider>);
    fireEvent.click(screen.getByText('open-a'));
    fireEvent.click(screen.getByText('close'));
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('Escape key closes the pane', () => {
    render(<ReportViewerProvider><Probe /></ReportViewerProvider>);
    fireEvent.click(screen.getByText('open-a'));
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('useReportViewer throws outside the provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow();
    spy.mockRestore();
  });

  it('setActiveBuilder and clearActiveBuilder manage the activeBuilder slot', () => {
    function BuilderProbe() {
      const { activeBuilder, setActiveBuilder, clearActiveBuilder } = useReportViewer();
      return (
        <div>
          <div data-testid="builder">{activeBuilder ? activeBuilder.title : 'none'}</div>
          <button onClick={() => setActiveBuilder({ title: 'My Report', buildMarkdown: () => '# md' })}>set</button>
          <button onClick={clearActiveBuilder}>clear</button>
        </div>
      );
    }
    render(<ReportViewerProvider><BuilderProbe /></ReportViewerProvider>);
    expect(screen.getByTestId('builder')).toHaveTextContent('none');
    fireEvent.click(screen.getByText('set'));
    expect(screen.getByTestId('builder')).toHaveTextContent('My Report');
    fireEvent.click(screen.getByText('clear'));
    expect(screen.getByTestId('builder')).toHaveTextContent('none');
  });
});
