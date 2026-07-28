import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import OverviewSkeleton from './OverviewSkeleton.jsx';

describe('OverviewSkeleton', () => {
  it('rides the real overview shell classes', () => {
    const { container } = render(<OverviewSkeleton projectName="acme" />);
    expect(container.querySelector('.acc-eval-panel.acc-eval-panel--terminal')).toBeTruthy();
    expect(container.querySelector('.acc-eval-panel__top')).toBeTruthy();
    expect(container.querySelector('.term-stat-strip.term-stat-strip--cards')).toBeTruthy();
    expect(container.querySelector('.quality-dimensions')).toBeTruthy();
    expect(container.querySelector('.quality-dimensions__head')).toBeTruthy();
    expect(container.querySelector('.dimensions-panel > .dimensions-grid')).toBeTruthy();
  });

  it('carries the "which project" loading signal in the TermHeader sub', () => {
    const { getByText } = render(<OverviewSkeleton projectName="acme" />);
    expect(getByText('loading acme…')).toBeTruthy();
  });

  it('renders a real TermHeader named overview', () => {
    const { container } = render(<OverviewSkeleton projectName="acme" />);
    const header = container.querySelector('.term-header');
    expect(header).toBeTruthy();
    expect(header.querySelector('.term-header__name').textContent).toBe('overview');
  });

  it('renders exactly 4 stat tiles', () => {
    const { container } = render(<OverviewSkeleton projectName="acme" />);
    expect(container.querySelectorAll('.term-stat').length).toBe(4);
  });

  it('renders exactly 6 dimension placeholder cards shaped like dim-gauge-card', () => {
    const { container } = render(<OverviewSkeleton projectName="acme" />);
    const cards = container.querySelectorAll('.dimensions-grid > .dim-gauge-card');
    expect(cards.length).toBe(6);
    const first = cards[0];
    expect(first.querySelector('.dim-gauge-card__head')).toBeTruthy();
    expect(first.querySelector('.dim-gauge-card__gauge')).toBeTruthy();
    expect(first.querySelector('.dim-gauge-card__meta')).toBeTruthy();
    expect(first.querySelector('.dim-gauge-card__sev-row')).toBeTruthy();
  });

  it('the quality_dimensions section label carries no count (the real count is unknown)', () => {
    const { getByText } = render(<OverviewSkeleton projectName="acme" />);
    expect(getByText('quality_dimensions')).toBeTruthy();
  });

  it('marks skeleton visuals aria-hidden and the container aria-busy', () => {
    const { container } = render(<OverviewSkeleton projectName="acme" />);
    expect(container.querySelector('.overview-skeleton')).toHaveAttribute('aria-busy', 'true');
    container.querySelectorAll('.term-stat').forEach((el) => {
      expect(el).toHaveAttribute('aria-hidden', 'true');
    });
    container.querySelectorAll('.dim-gauge-card').forEach((el) => {
      expect(el).toHaveAttribute('aria-hidden', 'true');
    });
  });

  it('falls back to a generic "loading…" sub when no project name is available yet', () => {
    const { getByText } = render(<OverviewSkeleton />);
    expect(getByText('loading…')).toBeTruthy();
  });
});
