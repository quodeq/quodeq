import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAnalyzeForm, inferRepoSource } from './useAnalyzeForm.js';
import { useWizardState } from './useWizardState.js';

const picks = vi.hoisted(() => ({ next: '/Volumes/work' }));
vi.mock('../../dashboard/hooks/useFolderPicker.jsx', () => ({
  useFolderPicker: () => ({ browseFolder: async () => picks.next, picker: null }),
}));

function setup() {
  return renderHook(() => {
    const wizard = useWizardState();
    const form = useAnalyzeForm({ wizard });
    return { wizard, form };
  });
}

describe('inferRepoSource', () => {
  it('reads schemes and scp-style addresses as urls, everything else as a folder', () => {
    expect(inferRepoSource('https://github.com/acme/billing.git')).toBe('url');
    expect(inferRepoSource('ssh://git@host/acme/billing')).toBe('url');
    expect(inferRepoSource('git@github.com:acme/billing.git')).toBe('url');
    expect(inferRepoSource('deploy@host.example:repos/billing')).toBe('url');
    expect(inferRepoSource('file:///Users/me/evals.git')).toBe('url');
    expect(inferRepoSource('/Users/me/code/app')).toBe('folder');
    expect(inferRepoSource('C:\\code\\app')).toBe('folder');
    expect(inferRepoSource('')).toBe('folder');
  });

  it('reads a host typed without a scheme as a url', () => {
    expect(inferRepoSource('github.com/acme/billing')).toBe('url');
  });
});

describe('useAnalyzeForm', () => {
  beforeEach(() => { localStorage.clear(); picks.next = '/Volumes/work'; });

  it('starts empty, cannot submit, and keeps the default working-copy root', () => {
    const { result } = setup();
    expect(result.current.form.repo).toBe('');
    expect(result.current.form.canSubmit).toBe(false);
    expect(result.current.form.workingCopy.root).toBe('~/quodeq/repos');
  });

  it('a typed url is a url source, named after the repository, and can submit', () => {
    const { result } = setup();
    act(() => result.current.form.setRepo('git@github.com:acme/billing.git'));
    expect(result.current.form.source).toBe('url');
    expect(result.current.form.workingCopy.name).toBe('billing');
    expect(result.current.form.workingCopy.path).toBe('~/quodeq/repos/billing');
    expect(result.current.form.canSubmit).toBe(true);
    expect(result.current.wizard.state.repo).toMatchObject({ source: 'url', value: 'git@github.com:acme/billing.git' });
    expect(result.current.form.request()).toEqual({ repo: 'git@github.com:acme/billing.git', source: 'url' });
  });

  it('a host without a scheme is a url source, sent as https', () => {
    const { result } = setup();
    act(() => result.current.form.setRepo('github.com/acme/billing'));
    expect(result.current.form.source).toBe('url');
    expect(result.current.form.workingCopy.name).toBe('billing');
    expect(result.current.form.request()).toEqual({ repo: 'https://github.com/acme/billing', source: 'url' });
  });

  it('a typed path is a folder source with no working copy', () => {
    const { result } = setup();
    act(() => result.current.form.setRepo('/Users/me/code/app'));
    expect(result.current.form.source).toBe('folder');
    expect(result.current.form.workingCopy.name).toBe('');
    expect(result.current.form.request()).toEqual({ repo: '/Users/me/code/app', source: 'folder' });
  });

  it('local folder fills the field from the picker; a cancelled pick leaves it alone', async () => {
    const { result } = setup();
    await act(async () => { await result.current.form.browseRepoFolder(); });
    expect(result.current.form.repo).toBe('/Volumes/work');
    expect(result.current.form.source).toBe('folder');
    picks.next = null;
    await act(async () => { await result.current.form.browseRepoFolder(); });
    expect(result.current.form.repo).toBe('/Volumes/work');
  });

  it('a changed root is remembered and sent for a url; reset goes back to the default', async () => {
    const { result } = setup();
    act(() => result.current.form.setRepo('https://github.com/acme/billing.git'));
    await act(async () => { await result.current.form.workingCopy.change(); });
    expect(result.current.form.workingCopy.path).toBe('/Volumes/work/billing');
    expect(result.current.form.request().cloneDest).toBe('/Volumes/work');
    expect(localStorage.getItem('quodeq.lastCloneRoot')).toBe('/Volumes/work');
    act(() => result.current.form.workingCopy.reset());
    expect(result.current.form.workingCopy.root).toBe('~/quodeq/repos');
    expect(result.current.form.request()).not.toHaveProperty('cloneDest');
  });
});
