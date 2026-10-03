import { describe, it, expect } from 'vitest';
import { standardBaseLabel, STANDARD_TYPES } from './useStandards.js';

describe('standardBaseLabel', () => {
  it('joins the family and its edition', () => {
    expect(standardBaseLabel({ type: STANDARD_TYPES.ISO, subtype: '25010' })).toBe('iso-25010');
    expect(standardBaseLabel({ type: STANDARD_TYPES.WCAG, subtype: '2.2' })).toBe('wcag-2.2');
  });

  it('shows the family alone when it has no edition', () => {
    expect(standardBaseLabel({ type: STANDARD_TYPES.QUODEQ })).toBe('quodeq');
    expect(standardBaseLabel({ type: STANDARD_TYPES.CUSTOM, subtype: null })).toBe('custom');
  });

  it('returns null for an unknown family so the caller can fall back', () => {
    expect(standardBaseLabel({ type: 'mystery', subtype: '1' })).toBeNull();
  });
});
