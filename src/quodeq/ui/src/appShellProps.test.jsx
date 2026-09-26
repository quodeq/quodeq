import { describe, it, expect } from 'vitest';
import { buildTopBarProps } from './appShellProps.js';

// buildTopBarProps used to read window.location.origin itself instead of
// taking serverUrl as an argument -- a hidden environment read inside an
// otherwise pure prop-builder. AppMain.jsx now computes window.location.origin
// once and passes it in, so this builder stays pure and testable without a
// DOM global.

const baseArgs = {
  resolvedDisplayName: 'Project',
  serverConnected: true,
  sidebarProvider: 'claude',
  sidebarModel: 'sonnet',
  selectedSource: 'local',
  projectsCount: 1,
  onEvaluateClick: () => {},
  evaluating: false,
  topbarRunProgress: null,
  navTab: () => {},
  setSidebarPinned: () => {},
  breadcrumb: null,
  mobileTitle: null,
  navStackLength: 1,
  navPop: () => {},
  effectiveDark: false,
  toggleTheme: () => {},
};

describe('buildTopBarProps', () => {
  it('uses the given serverUrl instead of reading window.location.origin itself', () => {
    const props = buildTopBarProps({ ...baseArgs, serverUrl: 'http://custom-host:9999' });
    expect(props.serverUrl).toBe('http://custom-host:9999');
  });

  it('two calls with different serverUrl values produce different output (no cached/global read)', () => {
    const a = buildTopBarProps({ ...baseArgs, serverUrl: 'http://host-a' });
    const b = buildTopBarProps({ ...baseArgs, serverUrl: 'http://host-b' });
    expect(a.serverUrl).toBe('http://host-a');
    expect(b.serverUrl).toBe('http://host-b');
  });
});
