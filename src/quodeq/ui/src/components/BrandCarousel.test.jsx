import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import BrandCarousel from './BrandCarousel.jsx';

describe('BrandCarousel', () => {
  it('renders the wordmark and an initial phrase', () => {
    const { container } = render(<BrandCarousel />);
    expect(container.querySelector('.sa-wordmark').textContent).toBe('quodeq');
    const phrase = container.querySelector('.sa-phrase');
    expect(phrase).not.toBeNull();
    expect(phrase.textContent.length).toBeGreaterThan(0);
  });

  it('exposes chevron hit targets for keyboard/click navigation', () => {
    const { container } = render(<BrandCarousel />);
    expect(container.querySelector('.sa-hit--left')).not.toBeNull();
    expect(container.querySelector('.sa-hit--right')).not.toBeNull();
  });
});
