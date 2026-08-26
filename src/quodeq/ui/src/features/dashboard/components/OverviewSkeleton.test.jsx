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

  // The real overview renders a chart+dimensions row and (usually) an
  // offending-files table below the gauge grid. The skeleton must reserve
  // both, or data arrival grows the page under the user.
  it('renders the history-panels row with both panel shells', () => {
    const { container } = render(<OverviewSkeleton projectName="acme" />);
    const row = container.querySelector('.history-panels-row');
    expect(row).toBeTruthy();
    expect(row.querySelector('.run-history-panel.run-history-panel--terminal.panel')).toBeTruthy();
    expect(row.querySelector('.run-history-panel__chart-slot')).toBeTruthy();
    expect(row.querySelector('.dim-score-panel.dim-score-panel--terminal.panel')).toBeTruthy();
  });

  it('places the history-panels row between the hero and the dimensions grid', () => {
    const { container } = render(<OverviewSkeleton projectName="acme" />);
    const children = Array.from(container.querySelector('.overview-skeleton').children);
    const heroIdx = children.findIndex((el) => el.classList.contains('acc-eval-panel'));
    const rowIdx = children.findIndex((el) => el.classList.contains('history-panels-row'));
    const gridIdx = children.findIndex((el) => el.classList.contains('quality-dimensions'));
    expect(heroIdx).toBeGreaterThanOrEqual(0);
    expect(rowIdx).toBeGreaterThan(heroIdx);
    expect(gridIdx).toBeGreaterThan(rowIdx);
  });

  it('renders 6 dimension-score placeholder rows carrying every slot the real row has', () => {
    const { container } = render(<OverviewSkeleton />);
    const rows = container.querySelectorAll('.dim-score-rows > .dim-score-row');
    expect(rows.length).toBe(6);
    ['label', 'spark', 'value', 'trend', 'viol'].forEach((slot) => {
      expect(rows[0].querySelector(`.dim-score-${slot} .overview-skeleton__bar`)).toBeTruthy();
    });
  });

  it('renders an offending-files placeholder section after the dimensions grid', () => {
    const { container } = render(<OverviewSkeleton />);
    const panel = container.querySelector('.qd-cards-panel.offending-panel');
    expect(panel).toBeTruthy();
    expect(panel).toHaveAttribute('aria-hidden', 'true');
    expect(panel.querySelectorAll('.overview-skeleton__file-row').length).toBeGreaterThan(2);
    const children = Array.from(container.querySelector('.overview-skeleton').children);
    const gridIdx = children.findIndex((el) => el.classList.contains('quality-dimensions'));
    const offIdx = children.findIndex((el) => el.classList.contains('offending-panel'));
    expect(offIdx).toBeGreaterThan(gridIdx);
  });

  it('marks the new sections aria-hidden', () => {
    const { container } = render(<OverviewSkeleton />);
    expect(container.querySelector('.history-panels-row')).toHaveAttribute('aria-hidden', 'true');
  });
});
