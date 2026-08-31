import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  saveDraft, loadDraft, clearDraft, DRAFT_KEY,
  markWelcomeSkipped, wasWelcomeSkipped, SKIPPED_KEY,
} from './useWizardDraft.js';

// Same fakeStorage shape as visibleStandards.test.jsx: a plain in-memory
// object standing in for localStorage, so a test can assert against an
// injected backend instead of the jsdom global.
function fakeStorage(initial = {}) {
  const map = { ...initial };
  return {
    getItem: (k) => (k in map ? map[k] : null),
    setItem: (k, v) => { map[k] = v; },
    removeItem: (k) => { delete map[k]; },
    _map: map,
  };
}

describe('useWizardDraft', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useRealTimers();
  });

  it('saveDraft writes state under DRAFT_KEY with savedAt timestamp', () => {
    saveDraft({ step: 'provider', repo: { value: '/r' } });
    const raw = localStorage.getItem(DRAFT_KEY);
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw);
    expect(parsed.step).toBe('provider');
    expect(typeof parsed.savedAt).toBe('number');
  });

  it('loadDraft returns the previously saved state', () => {
    saveDraft({ step: 'standard-launch' });
    expect(loadDraft().step).toBe('standard-launch');
  });

  it('loadDraft returns null when no draft exists', () => {
    expect(loadDraft()).toBeNull();
  });

  it('loadDraft returns null when draft is older than 24h', () => {
    const stale = { step: 'provider', savedAt: Date.now() - (25 * 60 * 60 * 1000) };
    localStorage.setItem(DRAFT_KEY, JSON.stringify(stale));
    expect(loadDraft()).toBeNull();
  });

  it('clearDraft removes the entry', () => {
    saveDraft({ step: 'welcome' });
    clearDraft();
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull();
  });

  it('saveDraft does not throw when localStorage is unavailable', () => {
    const originalSetItem = Storage.prototype.setItem;
    Storage.prototype.setItem = () => { throw new Error('quota'); };
    try {
      expect(() => saveDraft({ step: 'welcome' })).not.toThrow();
    } finally {
      Storage.prototype.setItem = originalSetItem;
    }
  });

  it('markWelcomeSkipped writes the literal "true" under SKIPPED_KEY', () => {
    markWelcomeSkipped();
    expect(localStorage.getItem(SKIPPED_KEY)).toBe('true');
    expect(SKIPPED_KEY).toBe('quodeq_onboarding_skipped');
  });

  it('wasWelcomeSkipped reflects the stored flag', () => {
    expect(wasWelcomeSkipped()).toBe(false);
    markWelcomeSkipped();
    expect(wasWelcomeSkipped()).toBe(true);
  });

  it('saveDraft/loadDraft/clearDraft thread an injected storage backend, leaving localStorage untouched', () => {
    const storage = fakeStorage();
    saveDraft({ step: 'provider' }, storage);
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull(); // real localStorage untouched
    expect(loadDraft(storage).step).toBe('provider');
    clearDraft(storage);
    expect(loadDraft(storage)).toBeNull();
    expect(storage.getItem(DRAFT_KEY)).toBeNull();
  });
});
