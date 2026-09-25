import { describe, it, expect } from 'vitest';
import {
  readStoredProject, readStoredSource, STORAGE_KEY, SOURCE_STORAGE_KEY, DEFAULT_SOURCE,
} from './projectStateStorage.js';

/** Minimal in-memory backend matching the Storage interface. */
const fake = (entries = {}) => ({
  data: { ...entries },
  getItem(key) { return key in this.data ? this.data[key] : null; },
  setItem(key, value) { this.data[key] = String(value); },
  removeItem(key) { delete this.data[key]; },
});

/** A backend that throws on every operation (private mode, quota exceeded). */
const hostile = () => ({
  getItem() { throw new Error('SecurityError'); },
  setItem() { throw new Error('QuotaExceededError'); },
});

describe('readStoredProject', () => {
  it('returns the stored project id under the byte-identical key', () => {
    expect(readStoredProject(fake({ [STORAGE_KEY]: 'p1' }))).toBe('p1');
  });

  it('returns "" when nothing is stored', () => {
    expect(readStoredProject(fake())).toBe('');
  });

  it('returns "" when storage throws', () => {
    expect(readStoredProject(hostile())).toBe('');
  });
});

describe('readStoredSource', () => {
  it('returns a valid stored source under the byte-identical key', () => {
    expect(readStoredSource(fake({ [SOURCE_STORAGE_KEY]: 'shared' }))).toBe('shared');
  });

  it('falls back to the default when nothing is stored', () => {
    expect(readStoredSource(fake())).toBe(DEFAULT_SOURCE);
  });

  it('falls back to the default for an invalid/tampered stored value', () => {
    expect(readStoredSource(fake({ [SOURCE_STORAGE_KEY]: 'bogus' }))).toBe(DEFAULT_SOURCE);
  });

  it('falls back to the default when storage throws', () => {
    expect(readStoredSource(hostile())).toBe(DEFAULT_SOURCE);
  });
});
