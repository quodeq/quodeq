import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CompareDuelView from './CompareDuelView.jsx';

const day = (n) => `2026-09-${String(n).padStart(2, '0')}T00:00:00.000Z`;
const row = (over) => ({
  id: over.name, name: over.name, score: 7, delta: 0.4, lastISO: day(20), commitsSince: 0,
  totalFiles: 200, analyzedFiles: 100, lang: 'py', coveragePct: null,
  totalViolations: 30, totalCompliance: 70, severity: { critical: 1, major: 4, minor: 9 },
  ...over,
});
const items = (pairs) => pairs.map(([key, a, b]) => ({ key, label: key, a, b, gap: Math.round((a - b) * 10) / 10 }));

function makeDuel(over = {}) {
  const sec = items([['auth', 9, 5], ['crypto', 6, 6.1], ['input', 5, 8], ['secrets', 6, 6.5], ['logging', 8, 7], ['session', 7, 7]]);
  return {
    a: row({ name: 'alpha', score: 7.5 }),
    b: row({ name: 'beta', score: 6.5, totalViolations: 60, analyzedFiles: 300, commitsSince: 12 }),
    ready: true,
    gap: 1,
    dimensions: [
      { key: 'security', label: 'security', a: 7, b: 6, gap: 1, shared: true },
      { key: 'usability', label: 'usability', a: 8, b: null, gap: null, shared: false },
    ],
    sharedCount: 1,
    principles: [{ key: 'security', label: 'security', items: sec }],
    trend: {
      a: [7, 7.3, 7, 7.3, 7.5].map((value, i) => ({ dateISO: day(i + 1), value })),
      b: [6, 6.4, 6, 6.4, 6.5].map((value, i) => ({ dateISO: day(i + 1), value })),
    },
    ...over,
  };
}

const renderDuel = (duel = makeDuel(), onOpenProject = vi.fn()) => render(<CompareDuelView duel={duel} onOpenProject={onOpenProject} />);

describe('CompareDuelView: verdict', () => {
  it('names the leader and grades the gap against run-to-run noise', () => {
    renderDuel();
    const verdict = screen.getByRole('group', { name: 'Head-to-head comparison' });
    expect(verdict).toHaveTextContent(/alpha leads beta by \+1\.0/);
    expect(verdict).toHaveTextContent(/clear gap/);
  });

  it('opens a project from its name in the sentence', async () => {
    const onOpenProject = vi.fn();
    renderDuel(makeDuel(), onOpenProject);
    const verdict = screen.getByRole('group', { name: 'Head-to-head comparison' });
    await userEvent.click(within(verdict).getAllByRole('button', { name: /beta/ })[0]);
    expect(onOpenProject).toHaveBeenCalledWith('beta');
  });

  it('says so when both projects still need an evaluation', () => {
    renderDuel(makeDuel({ ready: false }));
    expect(screen.getByText(/Both projects need a completed evaluation/)).toBeInTheDocument();
  });
});

describe('CompareDuelView: fairness strip', () => {
  it('reads cautions aloud, not only as a red mark', () => {
    renderDuel();
    const checks = screen.getByRole('list', { name: 'How comparable these two projects are' });
    expect(within(checks).getByText(/1 of 2 dimensions scored on both sides/)).toBeInTheDocument();
    expect(within(checks).getAllByText('caution:', { exact: false })).toHaveLength(2);
    expect(within(checks).getByText(/beta is 12 commits past its last scan/)).toBeInTheDocument();
  });
});

describe('CompareDuelView: gap sources and exposure', () => {
  it('splits the gap per shared dimension and keeps the rest as its own row', () => {
    renderDuel();
    const panel = screen.getByRole('region', { name: "Each dimension's share of the overall gap" });
    expect(within(panel).getByText('security')).toBeInTheDocument();
    expect(within(panel).getByText('not shared + rounding')).toBeInTheDocument();
  });

  it('normalises violations by analysed files', () => {
    renderDuel();
    const table = screen.getByRole('region', { name: /Exposure of both projects/ });
    const per100 = within(table).getByRole('row', { name: /violations per 100 files/ });
    expect(per100).toHaveTextContent('30.0');
    expect(per100).toHaveTextContent('20.0');
  });
});

describe('CompareDuelView: principles', () => {
  it("lists each side's biggest edges with the score's owner spelled out", () => {
    renderDuel();
    const panel = screen.getByRole('region', { name: 'Principle by principle' });
    expect(within(panel).getByRole('heading', { name: "alpha's biggest edges" })).toBeInTheDocument();
    expect(within(panel).getByText('alpha: 9.0')).toHaveClass('sr-only');
    expect(within(panel).getByRole('img', { name: /Principle scores, alpha across, beta up/ })).toBeInTheDocument();
  });

  it('drops the scatter when too few principles would make it a lone dot', () => {
    const duel = makeDuel({ principles: [{ key: 'security', label: 'security', items: items([['auth', 9, 5]]) }] });
    renderDuel(duel);
    const panel = screen.getByRole('region', { name: 'Principle by principle' });
    expect(within(panel).queryByRole('img')).toBeNull();
  });
});

describe('CompareDuelView: score table', () => {
  const table = () => screen.getByRole('region', { name: /Every dimension and principle score/ });

  it('is always on screen, with the tally a manager reads first', () => {
    renderDuel();
    expect(table()).toHaveTextContent(/alpha ahead on 1 of 1 shared dimensions, beta on 0, 0 even/);
    expect(table()).toHaveTextContent(/widest gap: security/);
  });

  it('opens one dimension into its principles, or all of them with the principles switch', async () => {
    renderDuel();
    const toggle = within(table()).getByRole('button', { name: /security/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(within(table()).queryByText('auth')).toBeNull();
    await userEvent.click(toggle);
    expect(within(table()).getByText('auth')).toBeInTheDocument();
    await userEvent.click(toggle);
    await userEvent.click(within(table()).getByRole('button', { name: 'principles' }));
    expect(within(table()).getByText('auth')).toBeInTheDocument();
  });

  it('sorts by gap first, by name on request', async () => {
    const duel = makeDuel();
    duel.dimensions = [...duel.dimensions, { key: 'apis', label: 'apis', a: 7, b: 6.8, gap: 0.2, shared: true }];
    renderDuel(duel);
    const order = () => [...table().querySelectorAll('.compare-duel-table__group > ul > li:first-child .compare-duel-table__label')]
      .map((n) => n.textContent.replace(/^[▸▾]/, ''));
    expect(order()).toEqual(['security', 'apis', 'usability']);
    await userEvent.click(within(table()).getByRole('button', { name: 'name' }));
    expect(within(table()).getByRole('button', { name: 'name' })).toHaveAttribute('aria-pressed', 'true');
    expect(order()).toEqual(['apis', 'security', 'usability']);
  });

  it('spells out whose score each number is', () => {
    renderDuel();
    expect(within(table()).getByText('alpha: 7.0')).toHaveClass('sr-only');
    expect(within(table()).getByText('beta: 6.0')).toHaveClass('sr-only');
  });
});
