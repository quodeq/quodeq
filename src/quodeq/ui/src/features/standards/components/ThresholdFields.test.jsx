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

  it('does NOT call onChangeParam for non-integer string inputs ("abc", "6.9")', () => {
    const onChangeParam = vi.fn();
    render(<ThresholdFields requirement={REQ} reqOverrides={{}} onChangeParam={onChangeParam} />);
    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: 'abc' } });
    expect(onChangeParam).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: '6.9' } });
    expect(onChangeParam).not.toHaveBeenCalled();
  });

  it('does NOT call onChangeParam when field is cleared, and shows effective value after blur', () => {
    const onChangeParam = vi.fn();
    render(<ThresholdFields requirement={REQ} reqOverrides={{ max_lines: 80 }} onChangeParam={onChangeParam} />);
    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '' } });
    expect(onChangeParam).not.toHaveBeenCalled();
    fireEvent.blur(input);
    expect(input).toHaveValue(80);
  });

  it('typing a valid value after clearing works correctly', () => {
    const onChangeParam = vi.fn();
    render(<ThresholdFields requirement={REQ} reqOverrides={{}} onChangeParam={onChangeParam} />);
    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '' } });
    expect(onChangeParam).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: '75' } });
    expect(onChangeParam).toHaveBeenCalledWith('max_lines', 75);
  });

  it('after reset, input shows the default value (external-change sync)', () => {
    const onChangeParam = vi.fn();
    const { rerender } = render(
      <ThresholdFields requirement={REQ} reqOverrides={{ max_lines: 80 }} onChangeParam={onChangeParam} />
    );
    const input = screen.getByLabelText('Max function lines');
    expect(input).toHaveValue(80);
    // Simulate external reset: override removed, effective value reverts to default (50)
    rerender(<ThresholdFields requirement={REQ} reqOverrides={{}} onChangeParam={onChangeParam} />);
    expect(input).toHaveValue(50);
  });
});
