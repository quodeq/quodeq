import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import FixFirstPanel, { FIX_FIRST_SHOWN } from './FixFirstPanel.jsx';

const v = (req, severity, file = 'a.py') => ({ req, severity, file, title: `${req} title`, principle: 'Fault Tolerance' });

function dims(count) {
  const violations = Array.from({ length: count }, (_, i) => v(`R-${i}`, 'minor'));
  violations.push(v('R-CRIT', 'critical'));
  return [{ dimension: 'reliability', violations }];
}

describe('FixFirstPanel', () => {
  it('ranks the critical requirement first', () => {
    render(<FixFirstPanel dimensions={dims(2)} />);
    const rows = screen.getAllByRole('row');
    expect(rows[0]).toHaveTextContent('R-CRIT');
  });

  it('caps the list and opens the rest from the footer', () => {
    render(<FixFirstPanel dimensions={dims(FIX_FIRST_SHOWN + 3)} />);
    expect(screen.getAllByRole('row')).toHaveLength(FIX_FIRST_SHOWN);
    fireEvent.click(screen.getByRole('button', { name: /show all 12 requirements/i }));
    expect(screen.getAllByRole('row')).toHaveLength(FIX_FIRST_SHOWN + 4);
    expect(screen.getByRole('button', { name: /show fewer/i })).toBeInTheDocument();
  });

  it('opens a requirement with its dimension and code', () => {
    const onRequirementClick = vi.fn();
    render(<FixFirstPanel dimensions={dims(1)} onRequirementClick={onRequirementClick} />);
    fireEvent.click(screen.getAllByRole('row')[0]);
    expect(onRequirementClick).toHaveBeenCalledWith(expect.objectContaining({ dimension: 'reliability', req: 'R-CRIT' }));
  });

  it('renders nothing without requirements', () => {
    const { container } = render(<FixFirstPanel dimensions={[{ dimension: 'x', violations: [] }]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
