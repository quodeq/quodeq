import { describe, it, expect, afterEach } from 'vitest';
import { confirmDialog } from './confirmDialog.js';

function pressKey(key) {
  document.dispatchEvent(new KeyboardEvent('keydown', { key }));
}

afterEach(() => {
  document.querySelectorAll('.qd-confirm-overlay').forEach((el) => el.remove());
});

describe('confirmDialog', () => {
  it('resolves true when the confirm button is clicked', async () => {
    const promise = confirmDialog({ title: 't', message: 'm' });
    const confirmBtn = document.querySelector('.qd-confirm-btn--confirm');
    confirmBtn.click();
    expect(await promise).toBe(true);
    expect(document.querySelector('.qd-confirm-overlay')).toBeNull();
  });

  it('resolves false when the cancel button is clicked', async () => {
    const promise = confirmDialog({ title: 't', message: 'm' });
    document.querySelector('.qd-confirm-btn--cancel').click();
    expect(await promise).toBe(false);
  });

  it('resolves false on Escape and true on Enter', async () => {
    const p1 = confirmDialog({ title: 't', message: 'm' });
    pressKey('Escape');
    expect(await p1).toBe(false);

    const p2 = confirmDialog({ title: 't', message: 'm' });
    pressKey('Enter');
    expect(await p2).toBe(true);
  });

  it('resolves false on outside (overlay) click', async () => {
    const promise = confirmDialog({ title: 't', message: 'm' });
    document.querySelector('.qd-confirm-overlay').click();
    expect(await promise).toBe(false);
  });

});

describe('confirmDialog checkbox + shell reuse', () => {
  it('reports { ok, checked } when checkboxLabel is set', async () => {
    const promise = confirmDialog({ title: 't', message: 'm', checkboxLabel: 'discard', checkboxDefault: true });
    const checkbox = document.querySelector('.qd-confirm-checkbox input');
    expect(checkbox.checked).toBe(true);
    document.querySelector('.qd-confirm-btn--confirm').click();
    expect(await promise).toEqual({ ok: true, checked: true });
  });

  it('reports checked:false on cancel even with the checkbox on', async () => {
    const promise = confirmDialog({ title: 't', message: 'm', checkboxLabel: 'discard', checkboxDefault: true });
    document.querySelector('.qd-confirm-btn--cancel').click();
    expect(await promise).toEqual({ ok: false, checked: false });
  });

  it('does not remove another dialog\'s overlay after it has already closed', async () => {
    // Regression guard for the shared-shell extraction: each dialog's
    // keydown listener must only fire its own onCancel/onConfirm, not a
    // still-open earlier dialog's.
    const first = confirmDialog({ title: 'first', message: 'm' });
    document.querySelector('.qd-confirm-btn--confirm').click();
    await first;
    const second = confirmDialog({ title: 'second', message: 'm' });
    pressKey('Escape');
    expect(await second).toBe(false);
  });
});
