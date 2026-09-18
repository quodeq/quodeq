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
