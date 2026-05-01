import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PrinciplesRadial from './PrinciplesRadial.jsx';

const FIVE_FULL = [
  { name: 'modifiability', score: 4.7, hasEvidence: true },
  { name: 'modularity',    score: 3.0, hasEvidence: true },
  { name: 'reusability',   score: 10,  hasEvidence: true },
  { name: 'testability',   score: 9.8, hasEvidence: true },
  { name: 'analyzability', score: 6.5, hasEvidence: true },
];

const ONE_INSUFFICIENT = [
  ...FIVE_FULL.slice(0, 4),
  { name: 'analyzability', score: null, hasEvidence: false },
];

describe('PrinciplesRadial', () => {
  it('renders one axis label per principle (including insufficient ones)', () => {
    render(<PrinciplesRadial principles={ONE_INSUFFICIENT} />);
    for (const p of ONE_INSUFFICIENT) {
      expect(screen.getByText(new RegExp(p.name, 'i'))).toBeInTheDocument();
    }
  });

  it('renders a filled polygon polyline when 3+ principles have evidence', () => {
    const { container } = render(<PrinciplesRadial principles={ONE_INSUFFICIENT} />);
    const poly = container.querySelector('polyline.qd-radial__poly');
    expect(poly).toBeTruthy();
    const pts = poly.getAttribute('points').trim().split(/\s+/);
    expect(pts.length).toBe(4);
  });

  it('renders a single dot and no polyline when only 1 principle has evidence', () => {
    const principles = FIVE_FULL.map((p, i) => ({ ...p, hasEvidence: i === 0 }));
    const { container } = render(<PrinciplesRadial principles={principles} />);
    expect(container.querySelector('polyline.qd-radial__poly')).toBeNull();
    expect(container.querySelectorAll('circle.qd-radial__vert').length).toBe(1);
  });

  it('renders a line segment (open polyline) when 2 principles have evidence', () => {
    const principles = FIVE_FULL.map((p, i) => ({ ...p, hasEvidence: i < 2 }));
    const { container } = render(<PrinciplesRadial principles={principles} />);
    const poly = container.querySelector('polyline.qd-radial__poly');
    expect(poly).toBeTruthy();
    expect(poly.getAttribute('fill')).toBe('none');
    const pts = poly.getAttribute('points').trim().split(/\s+/);
    expect(pts.length).toBe(2);
  });

  it('renders only axis frame and 0 vertices when 0 principles have evidence', () => {
    const principles = FIVE_FULL.map((p) => ({ ...p, hasEvidence: false, score: null }));
    const { container } = render(<PrinciplesRadial principles={principles} />);
    expect(container.querySelector('polyline.qd-radial__poly')).toBeNull();
    expect(container.querySelectorAll('circle.qd-radial__vert').length).toBe(0);
    expect(container.querySelectorAll('circle.qd-radial__vert--insuf').length).toBe(5);
  });

  it('calls onPrincipleClick with the principle name when a label is clicked', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<PrinciplesRadial principles={FIVE_FULL} onPrincipleClick={onClick} />);
    await user.click(screen.getByText(/reusability/i));
    expect(onClick).toHaveBeenCalledWith('reusability');
  });
});
