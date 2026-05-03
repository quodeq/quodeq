import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import EmptyStateWithTour from './EmptyStateWithTour.jsx';

describe('EmptyStateWithTour', () => {
  beforeEach(() => localStorage.clear());

  it('renders the heading and both CTAs', () => {
    render(<EmptyStateWithTour onAdd={() => {}} onTour={() => {}} />);
    expect(screen.getByRole('heading', { name: /no projects yet/i })).toBeInTheDocument();
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
});
