/**
 * #6580 - the dialog only closed via a backdrop click or the Cancel button;
 * there was no Escape-key dismissal and no focus management on mount,
 * despite role="dialog" aria-modal="true" already being present.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ThresholdImpactDialog from './ThresholdImpactDialog.jsx';

describe('ThresholdImpactDialog keyboard accessibility', () => {
  const setup = (props = {}) => {
    const onCancel = vi.fn(); const onSave = vi.fn(); const onSaveAndRescan = vi.fn();
    render(<ThresholdImpactDialog changedDimensions={['maintainability']}
      onCancel={onCancel} onSave={onSave} onSaveAndRescan={onSaveAndRescan} {...props} />);
    return { onCancel, onSave, onSaveAndRescan };
  };

  it('focuses a focusable element inside the dialog on mount', () => {
    setup();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toContainElement(document.activeElement);
  });

  it('Escape calls onCancel', () => {
    const { onCancel } = setup();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalled();
  });
});
