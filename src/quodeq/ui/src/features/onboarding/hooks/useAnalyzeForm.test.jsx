import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useAnalyzeForm } from './useAnalyzeForm.js';
import { useWizardState } from './useWizardState.js';

vi.mock('../../dashboard/hooks/useFolderPicker.jsx', () => ({
  useFolderPicker: () => ({ browseFolder: async () => '/Volumes/work', picker: null }),
}));

const DIMS = [
  { id: 'security', name: 'Security' },
  { id: 'performance', name: 'Performance' },
];
const codexDetected = async () => [
  { id: 'claude-code', classification: 'cli', detected: false },
  { id: 'codex-cli', classification: 'cli', detected: true, defaultModel: null },
];

function setup({ detect = codexDetected, standards = DIMS } = {}) {
  return renderHook(() => {
    const wizard = useWizardState();
    const form = useAnalyzeForm({ wizard, standards, detect });
    return { wizard, form };
  });
}

describe('useAnalyzeForm', () => {
  beforeEach(() => localStorage.clear());

  it('starts on the url source with the default standard and the default working-copy root', async () => {
    const { result } = setup();
    expect(result.current.form.source).toBe('url');
    expect(result.current.form.standard.ids).toEqual(['security', 'performance']);
    expect(result.current.form.standard.name).toBe('quodeq default standard');
    expect(result.current.form.workingCopy.root).toBe('~/quodeq/repos');
    expect(result.current.form.provider.status).toBe('detecting');
    expect(result.current.form.canSubmit).toBe(false);
    await waitFor(() => expect(result.current.form.provider.status).toBe('detected'));
  });

  it('the detected provider becomes the wizard provider under its server id', async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.form.provider.label).toBe('Codex CLI'));
    expect(result.current.wizard.state.provider).toMatchObject({ id: 'codex', classification: 'cli' });
  });

  it('a configured provider wins, collapses the screen, and carries its time limit', async () => {
    localStorage.setItem('cc-active-provider', 'ollama');
    localStorage.setItem('cc-ollama-model', 'gemma4:26b');
    localStorage.setItem('cc-ollama-time-limit', '0');
    const { result } = setup();
    expect(result.current.form.provider.configured).toBe(true);
    expect(result.current.form.collapsed).toBe(true);
    expect(result.current.wizard.state.provider).toMatchObject({ id: 'ollama', model: 'gemma4:26b' });
    expect(result.current.wizard.state.totalTimeLimitS).toBe(0);
    act(() => result.current.form.expand());
    expect(result.current.form.collapsed).toBe(false);
  });

  it('the working copy is named after the repository', () => {
    const { result } = setup();
    act(() => result.current.form.setRepo('git@github.com:acme/billing.git'));
    expect(result.current.form.workingCopy.name).toBe('billing');
    expect(result.current.form.workingCopy.path).toBe('~/quodeq/repos/billing');
    expect(result.current.wizard.state.repo.value).toBe('git@github.com:acme/billing.git');
  });

  it('switching source clears the repository', () => {
    const { result } = setup();
    act(() => result.current.form.setRepo('https://github.com/acme/billing'));
    act(() => result.current.form.setSource('folder'));
    expect(result.current.form.repo).toBe('');
    expect(result.current.wizard.state.repo.source).toBe('folder');
  });

  it('a changed root is remembered and sent; reset goes back to the server default', async () => {
    const { result } = setup();
    act(() => result.current.form.setRepo('https://github.com/acme/billing.git'));
    await act(async () => { await result.current.form.workingCopy.change(); });
    expect(result.current.form.workingCopy.path).toBe('/Volumes/work/billing');
    expect(result.current.form.request().cloneDest).toBe('/Volumes/work');
    expect(localStorage.getItem('quodeq.lastCloneRoot')).toBe('/Volumes/work');
    act(() => result.current.form.workingCopy.reset());
    expect(result.current.form.workingCopy.root).toBe('~/quodeq/repos');
    expect(result.current.form.request()).not.toHaveProperty('cloneDest');
    expect(localStorage.getItem('quodeq.lastCloneRoot')).toBeNull();
  });

  it('picking narrows the standards, never to none, and the wizard follows', () => {
    const { result } = setup();
    act(() => result.current.form.standard.pick('performance'));
    expect(result.current.form.standard.ids).toEqual(['security']);
    expect(result.current.form.standard.name).toBe('Security');
    act(() => result.current.form.standard.pick('security'));
    expect(result.current.form.standard.ids).toEqual(['security']);
    expect(Array.from(result.current.wizard.state.standardIds)).toEqual(['security']);
  });

  it('no provider found keeps the run disabled', async () => {
    const { result } = setup({ detect: async () => [] });
    act(() => result.current.form.setRepo('/tmp/app'));
    await waitFor(() => expect(result.current.form.provider.status).toBe('none'));
    expect(result.current.form.canSubmit).toBe(false);
  });
});
