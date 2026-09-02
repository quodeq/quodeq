import { describe, it, expect, afterEach } from 'vitest';
import { chooseDialog } from './chooseDialog.js';

function pressKey(key) {
  document.dispatchEvent(new KeyboardEvent('keydown', { key }));
}

afterEach(() => {
  document.querySelectorAll('.qd-confirm-overlay').forEach((el) => el.remove());
});

describe('chooseDialog', () => {
  it('resolves null immediately when actions is empty', async () => {
    const result = await chooseDialog({ title: 't', message: 'm', actions: [] });
    expect(result).toBeNull();
  });

  it('resolves the clicked action key', async () => {
    const promise = chooseDialog({
      title: 't', message: 'm',
      actions: [{ key: 'replace', label: 'Replace' }, { key: 'copy', label: 'Copy' }],
    });
    const buttons = document.querySelectorAll('.qd-confirm-actions button');
    // First button is Cancel; action buttons follow in order.
    buttons[2].click();
    expect(await promise).toBe('copy');
  });

  it('resolves null on cancel, Escape, and outside click', async () => {
    const p1 = chooseDialog({ title: 't', message: 'm', actions: [{ key: 'a', label: 'A' }] });
    document.querySelector('.qd-confirm-btn--cancel').click();
    expect(await p1).toBeNull();

    const p2 = chooseDialog({ title: 't', message: 'm', actions: [{ key: 'a', label: 'A' }] });
    pressKey('Escape');
    expect(await p2).toBeNull();

    const p3 = chooseDialog({ title: 't', message: 'm', actions: [{ key: 'a', label: 'A' }] });
    document.querySelector('.qd-confirm-overlay').click();
    expect(await p3).toBeNull();
  });

});

describe('chooseDialog focus behavior', () => {
  it('does not resolve on Enter (unlike confirmDialog)', async () => {
    const promise = chooseDialog({ title: 't', message: 'm', actions: [{ key: 'a', label: 'A' }] });
    pressKey('Enter');
    // Still pending; resolve it now via cancel so the test can finish.
    document.querySelector('.qd-confirm-btn--cancel').click();
    expect(await promise).toBeNull();
  });

  it('focuses Cancel when any action is danger', async () => {
    chooseDialog({
      title: 't', message: 'm',
      actions: [{ key: 'a', label: 'A', variant: 'danger' }],
    });
    expect(document.activeElement).toBe(document.querySelector('.qd-confirm-btn--cancel'));
  });

  it('focuses the last action when none is danger', async () => {
    chooseDialog({
      title: 't', message: 'm',
      actions: [{ key: 'a', label: 'A' }, { key: 'b', label: 'B', variant: 'primary' }],
    });
    const buttons = document.querySelectorAll('.qd-confirm-actions button');
    expect(document.activeElement).toBe(buttons[buttons.length - 1]);
  });
});
