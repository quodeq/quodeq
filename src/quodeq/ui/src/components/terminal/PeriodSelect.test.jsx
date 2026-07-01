import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import PeriodSelect from './PeriodSelect.jsx';

describe('PeriodSelect', () => {
  it('renders the three options and reflects the current value', () => {
    render(<PeriodSelect value="week" onChange={() => {}} />);
    const select = screen.getByLabelText('Group score history by');
    expect(select).toHaveValue('week');
    expect(screen.getByRole('option', { name: 'Day' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Week' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Month' })).toBeInTheDocument();
  });

  it('calls onChange with the selected value', () => {
    const onChange = vi.fn();
    render(<PeriodSelect value="day" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Group score history by'), { target: { value: 'month' } });
    expect(onChange).toHaveBeenCalledWith('month');
  });
});
