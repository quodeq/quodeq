import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import SeverityBadgeRow from './SeverityBadgeRow.jsx';

const severity = { critical: 6, major: 939, minor: 1232 };

function badge(container, level) {
  return container.querySelector(`.term-sev-badge--${level}`);
}

describe('SeverityBadgeRow deltas', () => {
  it('mixed directions: criticals up reads bad, majors down reads good, minor has none', () => {
    const { container } = render(<SeverityBadgeRow severity={severity} deltas={{ critical: 1, major: -83 }} />);
    const crit = badge(container, 'critical').querySelector('.term-sev-badge__delta');
    expect(crit).toHaveTextContent('+1');
    expect(crit.querySelector('.trend-badge-down')).not.toBeNull();
    const maj = badge(container, 'major').querySelector('.term-sev-badge__delta');
    expect(maj).toHaveTextContent('-83');
    expect(maj.querySelector('.trend-badge-up')).not.toBeNull();
    expect(badge(container, 'minor').querySelector('.term-sev-badge__delta')).toBeNull();
  });

  it('the arrow follows the number: more findings points up, fewer points down', () => {
    const { container } = render(<SeverityBadgeRow severity={severity} deltas={{ critical: 1, major: -83 }} />);
    const critArrow = badge(container, 'critical').querySelector('.trend-arrow');
    const majArrow = badge(container, 'major').querySelector('.trend-arrow');
    expect(critArrow.style.transform).toBe('rotate(38deg)');
    expect(majArrow.style.transform).toBe('rotate(142deg)');
  });

  it('no deltas: chips as today', () => {
    const { container } = render(<SeverityBadgeRow severity={severity} />);
    expect(container.querySelectorAll('.term-sev-badge__delta')).toHaveLength(0);
    expect(container.textContent).not.toMatch(/undefined|NaN/);
  });

  it('zero shows no arrow', () => {
    const { container } = render(<SeverityBadgeRow severity={severity} deltas={{ critical: 0, major: -7 }} />);
    expect(badge(container, 'critical').querySelector('.term-sev-badge__delta')).toBeNull();
    expect(badge(container, 'major').querySelector('.term-sev-badge__delta')).toHaveTextContent('-7');
  });

  it('a count that dropped to zero keeps its chip so the arrow shows', () => {
    const { container } = render(<SeverityBadgeRow severity={{ critical: 0, major: 5, minor: 0 }} deltas={{ critical: -3, major: 0 }} />);
    const crit = badge(container, 'critical');
    expect(crit).toHaveTextContent('0 crit');
    expect(crit.querySelector('.term-sev-badge__delta')).toHaveTextContent('-3');
    expect(badge(container, 'minor')).toBeNull();
  });
});
