import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import EmptyStateWithTour from './EmptyStateWithTour.jsx';

describe('EmptyStateWithTour', () => {
  beforeEach(() => localStorage.clear());

  it('renders the no-projects header text and both CTAs', () => {
    render(<EmptyStateWithTour onAdd={() => {}} onTour={() => {}} />);
    expect(screen.getByText(/no projects yet/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add a project/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /take the tour/i })).toBeInTheDocument();
  });

  it('Add a project clears skip flag and calls onAdd', () => {
    localStorage.setItem('quodeq_onboarding_skipped', 'true');
    const onAdd = vi.fn();
    render(<EmptyStateWithTour onAdd={onAdd} onTour={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /add a project/i }));
    expect(onAdd).toHaveBeenCalled();
    expect(localStorage.getItem('quodeq_onboarding_skipped')).toBeNull();
  });

  it('Take the tour clears skip flag and calls onTour', () => {
    localStorage.setItem('quodeq_onboarding_skipped', 'true');
    const onTour = vi.fn();
    render(<EmptyStateWithTour onAdd={() => {}} onTour={onTour} />);
    fireEvent.click(screen.getByRole('button', { name: /take the tour/i }));
    expect(onTour).toHaveBeenCalled();
    expect(localStorage.getItem('quodeq_onboarding_skipped')).toBeNull();
  });

  // Remote-content awareness: with a connected shared repo that has
  // published projects, the wall must offer a path to them, not only
  // "add a project" (spec 2026-07-23-remote-repos-without-local-projects).
  it('hides the browse-remote button when onBrowseRemote is not provided', () => {
    render(<EmptyStateWithTour onAdd={() => {}} onTour={() => {}} />);
    expect(screen.queryByRole('button', { name: /browse remote repositories/i })).toBeNull();
  });

  it('shows the browse-remote button and calls onBrowseRemote', () => {
    const onBrowseRemote = vi.fn();
    render(<EmptyStateWithTour onAdd={() => {}} onTour={() => {}} onBrowseRemote={onBrowseRemote} />);
    fireEvent.click(screen.getByRole('button', { name: /browse remote repositories/i }));
    expect(onBrowseRemote).toHaveBeenCalled();
  });

  it('browse-remote stays clickable during an evaluation (read-only path)', () => {
    const onBrowseRemote = vi.fn();
    render(<EmptyStateWithTour onAdd={() => {}} onTour={() => {}} onBrowseRemote={onBrowseRemote} isEvaluating />);
    fireEvent.click(screen.getByRole('button', { name: /browse remote repositories/i }));
    expect(onBrowseRemote).toHaveBeenCalled();
  });
});
