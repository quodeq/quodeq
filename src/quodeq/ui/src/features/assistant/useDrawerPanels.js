/**
 * Which drawer panels (assistant/terminal) are open, and which is active.
 * Each panel has an independent open/selected state; the topbar launchers
 * toggle a panel's membership, in-drawer tab clicks just change which open
 * panel is active. All the actual state-transition logic is the pure
 * drawerPanelsModel.js.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  openTabPanels, togglePanel, openPanelsIfClosed, togglePanels,
  closeActiveTabPanels, closeSpecificPanel, dropDisabledPanels, fallbackActiveTab,
} from './drawerPanelsModel.js';

export function useDrawerPanels({ assistantEnabled, terminalEnabled }) {
  const [openPanels, setOpenPanels] = useState([]);
  const [activeTab, setActiveTab] = useState('assistant');
  const activeTabRef = useRef('assistant');
  activeTabRef.current = activeTab;
  const isOpen = openPanels.length > 0;

  // Activate a panel, opening it if it isn't already (in-drawer tab click /
  // programmatic). Keeps any other open panel selected.
  const openTab = useCallback((tab) => {
    setActiveTab(tab);
    setOpenPanels((prev) => openTabPanels(prev, tab));
  }, []);
  // In-drawer title-bar tab click: just change which open panel is active.
  const selectTab = useCallback((tab) => setActiveTab(tab), []);
  // Topbar launcher / chord toggle.
  const toggleTopbar = useCallback((tab) => {
    setOpenPanels((prev) => {
      const result = togglePanel(prev, activeTabRef.current, tab);
      setActiveTab(result.activeTab);
      return result.openPanels;
    });
  }, []);

  // Open the drawer with the previously active tab; exposed on the context
  // for programmatic callers besides the keydown handler.
  const open = useCallback(() => {
    setOpenPanels((prev) => openPanelsIfClosed(prev, activeTabRef.current));
  }, []);
  const close = useCallback(() => setOpenPanels([]), []);          // close ALL panels
  const toggle = useCallback(() => {
    setOpenPanels((prev) => togglePanels(prev, activeTabRef.current));
  }, []);
  // Close just the ACTIVE tab: if another panel is still open the drawer stays
  // open and switches to it; only the last one closing hides the drawer.
  const closeActiveTab = useCallback(() => {
    setOpenPanels((prev) => {
      const result = closeActiveTabPanels(prev, activeTabRef.current);
      setActiveTab(result.activeTab);
      return result.openPanels;
    });
  }, []);
  // Close one SPECIFIC panel, active or not, leaving any other open panel
  // alone. If it was the active one, fall back to the most recent remaining
  // panel, same rule as closeActiveTab.
  const closePanel = useCallback((tab) => {
    setOpenPanels((prev) => {
      const result = closeSpecificPanel(prev, activeTabRef.current, tab);
      setActiveTab(result.activeTab);
      return result.openPanels;
    });
  }, []);

  // Drop any panel whose feature was disabled in Settings; keep the rest.
  useEffect(() => {
    setOpenPanels((prev) => dropDisabledPanels(prev, { assistantEnabled, terminalEnabled }));
  }, [assistantEnabled, terminalEnabled]);
  // If the active tab got closed/disabled, fall back to another open panel.
  useEffect(() => {
    const next = fallbackActiveTab(openPanels, activeTab);
    if (next !== activeTab) setActiveTab(next);
  }, [openPanels, activeTab]);

  return {
    openPanels, activeTab, isOpen,
    openTab, selectTab, toggleTopbar, open, close, toggle, closeActiveTab, closePanel,
  };
}
