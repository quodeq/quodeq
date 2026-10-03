import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { OnlineCardFooter } from './OnlineCardFooter.jsx';

describe('OnlineCardFooter — onPull guard', () => {
  it('does not throw when onPull is not provided', () => {
    render(<OnlineCardFooter projectId="p1" />);
    const btn = screen.getByRole('button');
    expect(() => fireEvent.click(btn)).not.toThrow();
  });

  it('calls onPull with the projectId when provided', () => {
    const onPull = vi.fn();
    render(<OnlineCardFooter projectId="p1" onPull={onPull} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onPull).toHaveBeenCalledWith('p1');
  });
});

describe('OnlineCardFooter — pulling', () => {
  it('shows "downloading…" with an indeterminate bar and a disabled button while the pull runs', () => {
    const onPull = vi.fn();
    render(<OnlineCardFooter projectId="p1" onPull={onPull} pulling />);
    const btn = screen.getByRole('button', { name: 'downloading…' });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onPull).not.toHaveBeenCalled();
    const bar = screen.getByRole('progressbar', { name: 'downloading a local copy' });
    expect(bar).toHaveAttribute('aria-busy', 'true');
    expect(bar).not.toHaveAttribute('aria-valuenow');
  });

  it('shows "pulled to local" once the pull is done', () => {
    render(<OnlineCardFooter projectId="p1" pulled />);
    expect(screen.getByText('pulled to local')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });
});
