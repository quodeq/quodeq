import { describe, it, expect, beforeEach, vi } from 'vitest';
import { saveDraft, loadDraft, clearDraft, DRAFT_KEY } from './useWizardDraft.js';

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
});
