import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ThresholdFields from './ThresholdFields.jsx';

const REQ = {
  id: 'M-ANA-2',
  text: 'Functions MUST NOT exceed {max_lines} lines',
  params: { max_lines: { label: 'Max function lines', type: 'int', default: 50, min: 10, max: 500 } },
};

describe('ThresholdFields', () => {
  it('shows one numeric input per declared param with the effective value', () => {
    render(<ThresholdFields requirement={REQ} reqOverrides={{ max_lines: 60 }} onChangeParam={() => {}} />);
    const input = screen.getByLabelText('Max function lines');
    expect(input).toHaveValue(60);
    expect(screen.getByText(/default 50/)).toBeInTheDocument();
    expect(screen.getByText(/10\s*–\s*500/)).toBeInTheDocument();
  });

  it('emits onChangeParam with the parsed integer', () => {
    const onChangeParam = vi.fn();
    render(<ThresholdFields requirement={REQ} reqOverrides={{}} onChangeParam={onChangeParam} />);
    fireEvent.change(screen.getByLabelText('Max function lines'), { target: { value: '60' } });
    expect(onChangeParam).toHaveBeenCalledWith('max_lines', 60);
  });

  it('reset emits null and is hidden when no override is active', () => {
    const onChangeParam = vi.fn();
    const { rerender } = render(
      <ThresholdFields requirement={REQ} reqOverrides={{ max_lines: 60 }} onChangeParam={onChangeParam} />);
    fireEvent.click(screen.getByRole('button', { name: /reset to default/i }));
    expect(onChangeParam).toHaveBeenCalledWith('max_lines', null);
    rerender(<ThresholdFields requirement={REQ} reqOverrides={{}} onChangeParam={onChangeParam} />);
    expect(screen.queryByRole('button', { name: /reset to default/i })).not.toBeInTheDocument();
  });
});
