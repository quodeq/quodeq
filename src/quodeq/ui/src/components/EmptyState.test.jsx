import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import EmptyState from './EmptyState.jsx';

describe('EmptyState', () => {
  it('renders the title as h2', () => {
    render(<EmptyState title="No projects yet" />);
    expect(screen.getByRole('heading', { level: 2, name: 'No projects yet' })).toBeInTheDocument();
  });

  it('renders the description when provided', () => {
    render(<EmptyState title="t" description="Run an evaluation to begin." />);
    expect(screen.getByText('Run an evaluation to begin.')).toBeInTheDocument();
  });

  it('omits the description when not provided', () => {
    const { container } = render(<EmptyState title="t" />);
    expect(container.querySelector('.empty-state p')).toBeNull();
  });

  it('renders the CTA button when both actionLabel and onAction are provided', () => {
    render(<EmptyState title="t" actionLabel="Start" onAction={() => {}} />);
    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  });

  it('does not render the CTA button when actionLabel is missing', () => {
    render(<EmptyState title="t" onAction={() => {}} />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('does not render the CTA button when onAction is missing', () => {
    render(<EmptyState title="t" actionLabel="Start" />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('calls onAction when the CTA is clicked', () => {
    const onAction = vi.fn();
    render(<EmptyState title="t" actionLabel="Start" onAction={onAction} />);
    fireEvent.click(screen.getByRole('button', { name: 'Start' }));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it('renders an icon when provided', () => {
    const { container } = render(
      <EmptyState title="t" icon={<svg data-testid="icon" />} />
    );
    expect(container.querySelector('.empty-state__icon')).not.toBeNull();
  });

  it('does not render the icon container when icon is omitted', () => {
    const { container } = render(<EmptyState title="t" />);
    expect(container.querySelector('.empty-state__icon')).toBeNull();
  });
});
