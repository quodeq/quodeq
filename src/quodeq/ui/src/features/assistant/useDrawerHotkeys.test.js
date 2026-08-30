import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveHotkeyTarget } from './useDrawerHotkeys.js';

const CTRL_BACKTICK = { code: 'Backquote', ctrlKey: true, shiftKey: false };
const META_BACKTICK = { code: 'Backquote', ctrlKey: false, metaKey: true, shiftKey: false };
const CTRL_SHIFT_BACKTICK = { code: 'Backquote', ctrlKey: true, shiftKey: true };

test('resolveHotkeyTarget: ignores keys that are not the Ctrl/Cmd+` combo', () => {
  assert.equal(resolveHotkeyTarget({ code: 'KeyA', ctrlKey: true }, { assistantEnabled: true, terminalEnabled: true }), null);
  assert.equal(resolveHotkeyTarget({ code: 'Backquote', ctrlKey: false, metaKey: false }, { assistantEnabled: true, terminalEnabled: true }), null);
});

test('resolveHotkeyTarget: Ctrl+` targets assistant when enabled, else falls back to terminal', () => {
  assert.equal(resolveHotkeyTarget(CTRL_BACKTICK, { assistantEnabled: true, terminalEnabled: true }), 'assistant');
  assert.equal(resolveHotkeyTarget(CTRL_BACKTICK, { assistantEnabled: false, terminalEnabled: true }), 'terminal');
  assert.equal(resolveHotkeyTarget(CTRL_BACKTICK, { assistantEnabled: false, terminalEnabled: false }), null);
});

test('resolveHotkeyTarget: Cmd+` (metaKey) is equivalent to Ctrl+`', () => {
  assert.equal(resolveHotkeyTarget(META_BACKTICK, { assistantEnabled: true, terminalEnabled: false }), 'assistant');
});

test('resolveHotkeyTarget: Ctrl+Shift+` targets the terminal ONLY, never assistant', () => {
  assert.equal(resolveHotkeyTarget(CTRL_SHIFT_BACKTICK, { assistantEnabled: true, terminalEnabled: true }), 'terminal');
  assert.equal(resolveHotkeyTarget(CTRL_SHIFT_BACKTICK, { assistantEnabled: true, terminalEnabled: false }), null);
});
