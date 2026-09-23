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

  // #6580 - the mount/unmount effect must fire once per open, not
  // once per onCancel identity: StandardEditor.jsx passes a fresh inline
  // arrow on every render, so a stale [onCancel] dependency tore the effect
  // down and back up on every parent re-render while the dialog stayed open,
  // yanking focus back to the first control each time.
  it('keeps focus where the user moved it when the parent re-renders with a new onCancel identity', () => {
    const onSave = vi.fn();
    const onSaveAndRescan = vi.fn();
    const { rerender } = render(
      <ThresholdImpactDialog changedDimensions={['maintainability']}
        onCancel={() => {}} onSave={onSave} onSaveAndRescan={onSaveAndRescan} />,
    );
    const buttons = screen.getAllByRole('button');
    buttons[1].focus();
    expect(document.activeElement).toBe(buttons[1]);

    // A fresh onCancel identity, same as StandardEditor's inline arrow would
    // produce on every re-render.
    rerender(
      <ThresholdImpactDialog changedDimensions={['maintainability']}
        onCancel={() => {}} onSave={onSave} onSaveAndRescan={onSaveAndRescan} />,
    );
    expect(document.activeElement).toBe(buttons[1]);
  });

  it('Tab from the last button wraps focus to the first', () => {
    setup();
    const buttons = screen.getAllByRole('button');
    const last = buttons[buttons.length - 1];
    last.focus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(document.activeElement).toBe(buttons[0]);
  });
});
