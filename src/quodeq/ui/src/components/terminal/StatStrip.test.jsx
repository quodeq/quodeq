import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { StatStrip, Stat, SevBadge } from './index.js';

// Returns every <button> that contains another <button> — invalid HTML and a
// hydration/accessibility bug. The overview's VIOLATIONS card is the canonical
// offender: a clickable Stat whose hint holds clickable SevBadges.
function nestedButtons(container) {
  return [...container.querySelectorAll('button')].filter((b) => b.querySelector('button'));
}

function renderViolationsCard({ onStat, onBadge } = {}) {
  return render(
    <StatStrip cards>
      <Stat
        label="VIOLATIONS"
        value={228}
        onClick={onStat}
        ariaLabel="Show all violations"
        hint={<SevBadge level="critical" count={1} format="count-abbr" onClick={onBadge} />}
      />
    </StatStrip>,
  );
}

describe('Stat with interactive hint', () => {
  it('does not nest a <button> inside a <button>', () => {
    const { container } = renderViolationsCard({ onStat: vi.fn(), onBadge: vi.fn() });
    expect(nestedButtons(container)).toHaveLength(0);
  });

  it('keeps the stat clickable as its own button', () => {
    const onStat = vi.fn();
    const onBadge = vi.fn();
    renderViolationsCard({ onStat, onBadge });
    fireEvent.click(screen.getByRole('button', { name: 'Show all violations' }));
    expect(onStat).toHaveBeenCalledTimes(1);
    expect(onBadge).not.toHaveBeenCalled();
  });

  it('keeps the severity badge independently clickable', () => {
    const onStat = vi.fn();
    const onBadge = vi.fn();
    renderViolationsCard({ onStat, onBadge });
    fireEvent.click(screen.getByRole('button', { name: 'critical severity' }));
    expect(onBadge).toHaveBeenCalledTimes(1);
    expect(onStat).not.toHaveBeenCalled();
  });

  it('publishes the value length so CSS can fit it to the card', () => {
    // The fit-to-card font size in terminal.css divides the card width by this
    // count. Without it a long word (a dimension name) overflows its card and
    // widens the whole strip.
    const { container } = render(
      <StatStrip cards>
        <Stat label="analyzing" value="maintainability" hint="next: performance" />
        <Stat label="files this run" value={285} trailing="/ 1037" />
        <Stat label="score" value={<em>9.0</em>} />
      </StatStrip>,
    );
    const values = [...container.querySelectorAll('.term-stat__value')];
    expect(values[0].style.getPropertyValue('--stat-value-len')).toBe('15');
    expect(values[1].style.getPropertyValue('--stat-value-len')).toBe('3');
    // Rich values carry no measurable length — no property, CSS default applies.
    expect(values[2].style.getPropertyValue('--stat-value-len')).toBe('');
  });

  it('renders a plain (non-button) card when not clickable', () => {
    const { container } = render(
      <StatStrip cards>
        <Stat label="SCORE" value="9.0" hint="grade B" />
      </StatStrip>,
    );
    expect(container.querySelectorAll('button')).toHaveLength(0);
    expect(screen.getByText('9.0')).toBeInTheDocument();
    expect(screen.getByText('grade B')).toBeInTheDocument();
  });
});
