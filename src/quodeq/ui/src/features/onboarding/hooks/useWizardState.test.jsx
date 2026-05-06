import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useWizardState } from './useWizardState.js';

describe('useWizardState', () => {
  it('initial state for fresh user starts at welcome with isFirstProject=true', () => {
    const { result } = renderHook(() => useWizardState({ initial: { isFirstProject: true } }));
    expect(result.current.state.step).toBe('welcome');
    expect(result.current.state.isFirstProject).toBe(true);
    expect(result.current.state.repoScanSubState).toBe('idle');
    expect(result.current.state.standardIds.size).toBe(0);
  });

  it('initial state for existing project starts at repo-scan with isFirstProject=false', () => {
    const { result } = renderHook(() =>
      useWizardState({ initial: { step: 'repo-scan', isFirstProject: false } }),
    );
    expect(result.current.state.step).toBe('repo-scan');
    expect(result.current.state.isFirstProject).toBe(false);
  });

  it('scan flow transitions idle → scanning → scanned and stores projectId+scan', () => {
    const { result } = renderHook(() => useWizardState());
    expect(result.current.state.repoScanSubState).toBe('idle');
    act(() => result.current.startScan());
    expect(result.current.state.repoScanSubState).toBe('scanning');
    act(() => result.current.succeedScan('uuid-1', { total_files: 42 }));
    expect(result.current.state.repoScanSubState).toBe('scanned');
    expect(result.current.state.projectId).toBe('uuid-1');
    expect(result.current.state.scan.total_files).toBe(42);
  });

  it('scan error transitions to error sub-state and preserves repo input', () => {
    const { result } = renderHook(() => useWizardState());
    act(() => result.current.setRepo({ source: 'local', value: '/path' }));
    act(() => result.current.startScan());
    act(() => result.current.failScan({ message: 'boom' }));
    expect(result.current.state.repoScanSubState).toBe('error');
    expect(result.current.state.repo.value).toBe('/path');
  });

  it('toggleStandard enforces single-select when isFirstProject=true', () => {
    const { result } = renderHook(() => useWizardState({ initial: { isFirstProject: true } }));
    act(() => result.current.toggleStandard('std-a'));
    act(() => result.current.toggleStandard('std-b'));
    expect(result.current.state.standardIds.size).toBe(1);
    expect(result.current.state.standardIds.has('std-b')).toBe(true);
  });

  it('toggleStandard allows multi-select when isFirstProject=false', () => {
    const { result } = renderHook(() => useWizardState({ initial: { isFirstProject: false } }));
    act(() => result.current.toggleStandard('std-a'));
    act(() => result.current.toggleStandard('std-b'));
    expect(result.current.state.standardIds.size).toBe(2);
  });

  it('toggleStandard deselects when called twice with the same id', () => {
    const { result } = renderHook(() => useWizardState({ initial: { isFirstProject: false } }));
    act(() => result.current.toggleStandard('std-a'));
    act(() => result.current.toggleStandard('std-a'));
    expect(result.current.state.standardIds.size).toBe(0);
  });
});
