import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ThresholdImpactDialog from './ThresholdImpactDialog.jsx';

describe('ThresholdImpactDialog', () => {
  const setup = (props = {}) => {
    const onCancel = vi.fn(); const onSave = vi.fn(); const onSaveAndRescan = vi.fn();
    render(<ThresholdImpactDialog changedDimensions={['maintainability']}
      onCancel={onCancel} onSave={onSave} onSaveAndRescan={onSaveAndRescan} {...props} />);
    return { onCancel, onSave, onSaveAndRescan };
  };

  it('names the affected dimensions', () => {
    setup();
    expect(screen.getByRole('dialog')).toHaveTextContent('maintainability');
  });

  it('fires the matching callback per button', () => {
    const { onCancel, onSave, onSaveAndRescan } = setup();
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    fireEvent.click(screen.getByRole('button', { name: /re-scan/i }));
    expect(onCancel).toHaveBeenCalled();
    expect(onSave).toHaveBeenCalled();
    expect(onSaveAndRescan).toHaveBeenCalled();
  });

  it('omits the re-scan button when no handler is given', () => {
    setup({ onSaveAndRescan: undefined });
    expect(screen.queryByRole('button', { name: /re-scan/i })).toBeNull();
  });
});
