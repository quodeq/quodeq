import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HelpPage from './HelpPage.jsx';

// BrandCarousel auto-advances on a timer; stub it out for determinism.
vi.mock('../../../components/BrandCarousel.jsx', () => ({
  default: () => null,
}));

describe('HelpPage grade formula section', () => {
  it('lists Grade Formula in the section nav right after History & Trends', () => {
    render(<HelpPage />);
    const nav = screen.getByRole('button', { name: 'Grade Formula' });
    expect(nav.previousSibling).toHaveTextContent('History & Trends');
  });

  it('renders the Grade Formula section when selected', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Grade Formula' }));
    expect(screen.getByRole('heading', { level: 2, name: 'Grade Formula' })).toBeInTheDocument();
    expect(screen.getByText('SEVERITY')).toBeInTheDocument();
    expect(screen.getByText(/RESET Q²/)).toBeInTheDocument();
  });
});

describe('HelpPage history section', () => {
  it('documents day, week, month score grouping', () => {
    render(<HelpPage />);
    fireEvent.click(screen.getByRole('button', { name: 'History & Trends' }));
    expect(screen.getByRole('heading', { level: 3, name: /Group by day, week, or month/ })).toBeInTheDocument();
  });
});
