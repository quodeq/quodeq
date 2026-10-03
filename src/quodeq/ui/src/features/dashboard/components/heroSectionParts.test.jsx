import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { RatioDensityStat, ScoreStat, ratioDisplay } from './heroSectionParts.jsx';

describe('RatioDensityStat', () => {
  it('ratio is the number; density is the tile\'s second hint line, one decimal, no "?"', () => {
    const { container } = render(<RatioDensityStat ratio="1:3" density={12.64} />);
    expect(screen.getByText('RATIO')).toBeInTheDocument();
    expect(screen.getByText('1:3')).toBeInTheDocument();
    expect(screen.getByText('violations : compliance')).toBeInTheDocument();
    expect(screen.getByText('12.6')).toBeInTheDocument();
    expect(screen.getByText(/violations : 100 files/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(container.querySelectorAll('.term-stat__hint-line')).toHaveLength(2);
  });

  it('no density: ratio alone, no dash', () => {
    const { container } = render(<RatioDensityStat ratio="1:3" density={null} />);
    expect(screen.getByText('RATIO')).toBeInTheDocument();
    expect(container.querySelectorAll('.term-stat__hint-line')).toHaveLength(1);
    expect(container.textContent).not.toMatch(/(^|\s)[-—](\s|$)/);
  });

  it('ratioDisplay reads 0:N without violations, never a dash', () => {
    expect(ratioDisplay(0, 1922)).toBe('0:1922');
    expect(ratioDisplay(2177, 1922)).toBe('1:1');
  });

  it('ScoreStat puts the grade chip and the trend under the number, like the violation chips', () => {
    const { container } = render(<ScoreStat scoreDisplay="9.0" grade="Exemplary" extraTrailing={<span className="trend-badge">-0.1</span>} />);
    const hint = container.querySelector('.term-stat__hint');
    expect(hint.querySelector('.chip')).toHaveTextContent('EXEMPLARY');
    expect(hint.querySelector('.trend-badge')).toHaveTextContent('-0.1');
    expect(container.querySelector('.term-stat__trailing')).toBeNull();
  });
});
