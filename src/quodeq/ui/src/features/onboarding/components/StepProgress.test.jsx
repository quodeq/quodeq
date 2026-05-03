import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import StepProgress from './StepProgress.jsx';

describe('StepProgress', () => {
  it('renders "Step 2 of 3" with correct progress bar width', () => {
    const { container } = render(<StepProgress current={2} total={3} />);
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument();
    const bar = container.querySelector('.step-progress__fill');
    expect(bar).toHaveStyle('width: 66.66666666666666%');
  });

  it('renders nothing when total=0', () => {
    const { container } = render(<StepProgress current={1} total={0} />);
    expect(container.firstChild).toBeNull();
  });

  it('clamps current to [1, total]', () => {
    render(<StepProgress current={5} total={3} />);
    expect(screen.getByText('Step 3 of 3')).toBeInTheDocument();
  });
});
