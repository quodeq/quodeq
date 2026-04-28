import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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
  it('renders the title and body', () => {
    render(<SidePaneWindow spec={makeSpec()} onClose={() => {}} />);
    expect(screen.getByText('My Window')).toBeInTheDocument();
    expect(screen.getByText('body content')).toBeInTheDocument();
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
