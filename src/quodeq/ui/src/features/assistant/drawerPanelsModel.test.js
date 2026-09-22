import test from 'node:test';
import assert from 'node:assert/strict';
import {
  openTabPanels, togglePanel, openPanelsIfClosed, togglePanels,
  closeActiveTabPanels, closeSpecificPanel, dropDisabledPanels, fallbackActiveTab,
} from './drawerPanelsModel.js';

// ---------------------------------------------------------------------------
// openTabPanels
// ---------------------------------------------------------------------------

test('openTabPanels: opens a panel not yet in the set', () => {
  assert.deepEqual(openTabPanels(['assistant'], 'terminal'), ['assistant', 'terminal']);
});

test('openTabPanels: no-op (same reference) when already open', () => {
  const openPanels = ['assistant'];
  assert.equal(openTabPanels(openPanels, 'assistant'), openPanels);
});

// ---------------------------------------------------------------------------
// togglePanel — real branchy logic, previously zero direct coverage
// ---------------------------------------------------------------------------

test('togglePanel: opens and activates a closed panel', () => {
  assert.deepEqual(togglePanel([], 'assistant', 'terminal'), { openPanels: ['terminal'], activeTab: 'terminal' });
});

test('togglePanel: an open but non-active panel just becomes active (stays open)', () => {
  assert.deepEqual(
    togglePanel(['assistant', 'terminal'], 'assistant', 'terminal'),
    { openPanels: ['assistant', 'terminal'], activeTab: 'terminal' },
  );
});

test('togglePanel: re-pressing the already-active panel closes it, falling back to another open one', () => {
  assert.deepEqual(
    togglePanel(['assistant', 'terminal'], 'terminal', 'terminal'),
    { openPanels: ['assistant'], activeTab: 'assistant' },
  );
});

test('togglePanel: closing the last open (and active) panel leaves activeTab unchanged', () => {
  assert.deepEqual(
    togglePanel(['assistant'], 'assistant', 'assistant'),
    { openPanels: [], activeTab: 'assistant' },
  );
});

// ---------------------------------------------------------------------------
// openPanelsIfClosed / togglePanels
// ---------------------------------------------------------------------------

test('openPanelsIfClosed: opens with the given tab when closed, no-ops when already open', () => {
  assert.deepEqual(openPanelsIfClosed([], 'assistant'), ['assistant']);
  const openPanels = ['terminal'];
  assert.equal(openPanelsIfClosed(openPanels, 'assistant'), openPanels);
});

test('togglePanels: closes everything when open, reopens with the given tab when closed', () => {
  assert.deepEqual(togglePanels(['assistant'], 'assistant'), []);
  assert.deepEqual(togglePanels([], 'assistant'), ['assistant']);
});

// ---------------------------------------------------------------------------
// closeActiveTabPanels / closeSpecificPanel
// ---------------------------------------------------------------------------

test('closeActiveTabPanels: closes the active tab and activates the next-most-recent', () => {
  assert.deepEqual(
    closeActiveTabPanels(['assistant', 'terminal'], 'terminal'),
    { openPanels: ['assistant'], activeTab: 'assistant' },
  );
});

test('closeActiveTabPanels: closing the last panel leaves activeTab unchanged', () => {
  assert.deepEqual(
    closeActiveTabPanels(['assistant'], 'assistant'),
    { openPanels: [], activeTab: 'assistant' },
  );
});

test('closeSpecificPanel: no-op when the panel is not open', () => {
  const openPanels = ['assistant'];
  assert.deepEqual(closeSpecificPanel(openPanels, 'assistant', 'terminal'), { openPanels, activeTab: 'assistant' });
});

test('closeSpecificPanel: closing the active one falls back; closing a non-active one leaves activeTab alone', () => {
  assert.deepEqual(
    closeSpecificPanel(['assistant', 'terminal'], 'terminal', 'terminal'),
    { openPanels: ['assistant'], activeTab: 'assistant' },
  );
  assert.deepEqual(
    closeSpecificPanel(['assistant', 'terminal'], 'terminal', 'assistant'),
    { openPanels: ['terminal'], activeTab: 'terminal' },
  );
});

// ---------------------------------------------------------------------------
// dropDisabledPanels / fallbackActiveTab
// ---------------------------------------------------------------------------

test('dropDisabledPanels: drops a panel whose feature flag turned off', () => {
  assert.deepEqual(
    dropDisabledPanels(['assistant', 'terminal'], { assistantEnabled: true, terminalEnabled: false }),
    ['assistant'],
  );
});

test('dropDisabledPanels: same reference (no-op) when nothing needs dropping', () => {
  const openPanels = ['assistant'];
  assert.equal(dropDisabledPanels(openPanels, { assistantEnabled: true, terminalEnabled: true }), openPanels);
});

test('fallbackActiveTab: falls back to the last open panel when the active one is gone', () => {
  assert.equal(fallbackActiveTab(['terminal'], 'assistant'), 'terminal');
});

test('fallbackActiveTab: leaves activeTab alone when it is still open, or nothing is open', () => {
  assert.equal(fallbackActiveTab(['assistant', 'terminal'], 'terminal'), 'terminal');
  assert.equal(fallbackActiveTab([], 'assistant'), 'assistant');
});
