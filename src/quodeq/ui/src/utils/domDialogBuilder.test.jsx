import { describe, it, expect, vi, afterEach } from 'vitest';
import { buildDialogShell } from './domDialogBuilder.js';

afterEach(() => { document.body.innerHTML = ''; });

function open(extra = {}) {
  const shell = buildDialogShell({ title: 'T', message: 'M', dialogClassName: 'd', onCancel: vi.fn(), onConfirm: vi.fn(), ...extra });
  const ok = document.createElement('button');
  ok.textContent = 'ok';
  const no = document.createElement('button');
  no.textContent = 'no';
  shell.actionsEl.append(no, ok);
  shell.mount();
  return { ...shell, ok, no };
}

describe('dialog shell accessibility', () => {
  it('names the dialog by its title and describes it by its message', () => {
    const { overlay, titleEl, messageEl } = open();
    expect(titleEl.id).toBeTruthy();
    expect(overlay.getAttribute('aria-labelledby')).toBe(titleEl.id);
    expect(overlay.getAttribute('aria-describedby')).toBe(messageEl.id);
  });

  it('two dialogs get distinct title ids', () => {
    const a = open();
    const b = open();
    expect(a.titleEl.id).not.toBe(b.titleEl.id);
  });

  it('moves focus into the dialog on mount', () => {
    const outside = document.createElement('button');
    document.body.appendChild(outside);
    outside.focus();
    const { no } = open();
    expect(document.activeElement).toBe(no);
  });

  it('keeps Tab inside the dialog', () => {
    const { ok, no } = open();
    ok.focus();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(document.activeElement).toBe(no);
  });

  it('leaves Enter to the focused action button instead of confirming', () => {
    const onConfirm = vi.fn();
    const { no } = open({ onConfirm });
    no.focus();
    no.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('confirms on Enter when no action button has focus', () => {
    const onConfirm = vi.fn();
    const { overlay } = open({ onConfirm });
    overlay.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('restores focus to the opener on unmount', () => {
    const outside = document.createElement('button');
    document.body.appendChild(outside);
    outside.focus();
    const shell = open();
    shell.unmount();
    expect(document.activeElement).toBe(outside);
  });
});
