import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PrinciplesCardsRow from './PrinciplesCardsRow.jsx';

const PRINCIPLES = [
  { principle: 'modifiability', score: '4.7', grade: 'Poor', violationCount: 116, severity: { critical: 0, major: 11, minor: 105 } },
  { principle: 'analyzability', grade: 'Insufficient' },
];

describe('PrinciplesCardsRow', () => {
  it('renders one card per principle', () => {
    render(<PrinciplesCardsRow principles={PRINCIPLES} onPrincipleClick={() => {}} />);
    expect(screen.getByText('modifiability')).toBeInTheDocument();
    expect(screen.getByText('analyzability')).toBeInTheDocument();
  });

  it('renders insufficient state for grade=Insufficient', () => {
    render(<PrinciplesCardsRow principles={PRINCIPLES} onPrincipleClick={() => {}} />);
    expect(screen.getByText('INSUFFICIENT')).toBeInTheDocument();
    expect(screen.getByText('insufficient evidence')).toBeInTheDocument();
  });

  it('forwards click to onPrincipleClick with the principle name', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<PrinciplesCardsRow principles={PRINCIPLES} onPrincipleClick={onClick} />);
    await user.click(screen.getByText('modifiability'));
    expect(onClick).toHaveBeenCalledWith('modifiability');
  });
});
