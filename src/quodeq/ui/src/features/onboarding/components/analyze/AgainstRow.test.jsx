import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import AgainstRow from './AgainstRow.jsx';

const standards = [
  { id: 'security', name: 'Security' },
  { id: 'performance', name: 'Performance' },
];

function standard(over = {}) {
  return {
    ids: ['security', 'performance'], name: 'quodeq default standard', dimensions: ['security', 'performance'],
    pickerOpen: false, openPicker: vi.fn(), closePicker: vi.fn(), pick: vi.fn(), ...over,
  };
}

describe('AgainstRow', () => {
  it('names the standard and its dimensions; change opens the picker', () => {
    const s = standard();
    render(<AgainstRow standard={s} standards={standards} />);
    expect(screen.getByText('Against')).toBeInTheDocument();
    expect(screen.getByText('quodeq default standard')).toBeInTheDocument();
    expect(screen.getByText('security, performance')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'change the standard' }));
    expect(s.openPicker).toHaveBeenCalledTimes(1);
  });

  it('the open picker lists every standard, checked by the pick, and a click picks', () => {
    const s = standard({ pickerOpen: true, ids: ['security'] });
    render(<AgainstRow standard={s} standards={standards} />);
    expect(screen.getByRole('checkbox', { name: 'Security' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Performance' })).not.toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Performance' }));
    expect(s.pick).toHaveBeenCalledWith('performance');
    fireEvent.click(screen.getByRole('button', { name: 'done' }));
    expect(s.closePicker).toHaveBeenCalledTimes(1);
  });
});
