/**
 * Pure open-panels/active-tab transitions for the assistant drawer.
 * `openPanels` is the set of panels currently in the drawer (in selection
 * order); the drawer is open iff it's non-empty. Each function returns the
 * new derived state — useDrawerPanels.js is the only caller and owns
 * threading these through React state.
 */

/** openTab: open a panel if not already open (always activates it). */
export function openTabPanels(openPanels, tab) {
  return openPanels.includes(tab) ? openPanels : [...openPanels, tab];
}

/**
 * toggleTopbar: the topbar launcher / chord toggle. Opens+activates a
 * closed panel; re-pressing the ALREADY-active one closes it (falling back
 * to the next-most-recent open panel); pressing a different already-open
 * panel just activates it.
 */
export function togglePanel(openPanels, activeTab, tab) {
  if (!openPanels.includes(tab)) return { openPanels: [...openPanels, tab], activeTab: tab };
  if (activeTab !== tab) return { openPanels, activeTab: tab };
  const next = openPanels.filter((t) => t !== tab);
  return { openPanels: next, activeTab: next.length ? next[next.length - 1] : activeTab };
}

/** open(): open the drawer with the given (previously active) tab, if closed. */
export function openPanelsIfClosed(openPanels, activeTab) {
  return openPanels.length ? openPanels : [activeTab];
}

/** toggle(): close all panels, or reopen with the given (last active) tab. */
export function togglePanels(openPanels, activeTab) {
  return openPanels.length ? [] : [activeTab];
}

/** closeActiveTab(): close just the active tab, falling back to another open one. */
export function closeActiveTabPanels(openPanels, activeTab) {
  const next = openPanels.filter((t) => t !== activeTab);
  return { openPanels: next, activeTab: next.length ? next[next.length - 1] : activeTab };
}

/** closePanel(tab): close one specific panel, active or not. */
export function closeSpecificPanel(openPanels, activeTab, tab) {
  if (!openPanels.includes(tab)) return { openPanels, activeTab };
  const next = openPanels.filter((t) => t !== tab);
  const nextActive = (next.length && activeTab === tab) ? next[next.length - 1] : activeTab;
  return { openPanels: next, activeTab: nextActive };
}

/** Drop any panel whose feature was disabled in Settings; keep the rest. */
export function dropDisabledPanels(openPanels, { assistantEnabled, terminalEnabled }) {
  const next = openPanels.filter((t) => (t === 'assistant' ? assistantEnabled : terminalEnabled));
  return next.length === openPanels.length ? openPanels : next;
}

/** If the active tab got closed/disabled, fall back to another open panel. */
export function fallbackActiveTab(openPanels, activeTab) {
  if (openPanels.length && !openPanels.includes(activeTab)) {
    return openPanels[openPanels.length - 1];
  }
  return activeTab;
}
