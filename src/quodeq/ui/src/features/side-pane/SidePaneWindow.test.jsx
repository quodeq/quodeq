import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneWindow } from './SidePaneWindow.jsx';

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

function makeSpec(overrides = {}) {
  return {
    id: 'w1',
    type: 'report',
    title: 'My Window',
    render: () => <p>body content</p>,
    ...overrides,
  };
}

describe('SidePaneWindow', () => {
  it('renders the title immediately and the body once the slide-in defer finishes', async () => {
    render(<SidePaneWindow spec={makeSpec()} onClose={() => {}} />);
    expect(screen.getByText('My Window')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('body content')).toBeInTheDocument();
    });
  });

  it('Close button calls onClose with the window id', () => {
    const onClose = vi.fn();
    render(<SidePaneWindow spec={makeSpec({ id: 'abc' })} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /close window/i }));
    expect(onClose).toHaveBeenCalledWith('abc');
  });

  it('Copy button writes the result of spec.copy() to the clipboard', () => {
    render(<SidePaneWindow spec={makeSpec({ copy: () => 'clip!' })} onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /copy/i }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('clip!');
  });

  it('omits the Copy button when spec.copy is not provided', () => {
    render(<SidePaneWindow spec={makeSpec()} onClose={() => {}} />);
    expect(screen.queryByRole('button', { name: /copy/i })).toBeNull();
  });

  it('omits the Download button when spec.download is not provided', () => {
    render(<SidePaneWindow spec={makeSpec()} onClose={() => {}} />);
    expect(screen.queryByRole('button', { name: /download/i })).toBeNull();
  });

  it('Download button triggers spec.download() (smoke test only)', () => {
    const downloadFn = vi.fn(() => ({ filename: 'x.md', body: '# x' }));
    render(<SidePaneWindow spec={makeSpec({ download: downloadFn })} onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /download/i }));
    expect(downloadFn).toHaveBeenCalled();
  });
});

describe('RenderBoundary inside SidePaneWindow', () => {
  let consoleErrorSpy;

  beforeEach(() => {
    // Suppress React's own error boundary console output during the test
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('#454 — componentDidCatch calls console.error with the error and info', async () => {
    // A child that throws during render
    function ThrowingChild() {
      throw new Error('render kaboom');
    }

    const throwingSpec = {
      id: 'err-win',
      type: 'report',
      title: 'Error Window',
      render: () => <ThrowingChild />,
    };

    render(<SidePaneWindow spec={throwingSpec} onClose={() => {}} />);

    // Wait for the deferred body mount (SLIDE_MS = 220ms) so RenderBoundary renders
    await waitFor(() => {
      expect(screen.getByText(/Failed to render report/i)).toBeInTheDocument();
    }, { timeout: 1000 });

    // console.error must have been called by componentDidCatch (not just React internals)
    const boundaryCall = consoleErrorSpy.mock.calls.find(
      (args) => typeof args[0] === 'string' && args[0].includes('[SidePaneWindow]')
    );
    expect(boundaryCall).toBeDefined();
    expect(boundaryCall[0]).toContain('[SidePaneWindow] render error:');
    expect(boundaryCall[1]).toBeInstanceOf(Error);
  });
});
