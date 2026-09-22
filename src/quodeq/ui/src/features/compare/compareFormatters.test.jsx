import { describe, expect, it } from 'vitest';
import { nf, score1, signed1 } from './compareFormatters.js';

describe('compareFormatters', () => {
  it('score1 rounds to one decimal and shows a dash for null', () => {
    expect(score1(8.25)).toBe('8.3');
    expect(score1(7)).toBe('7.0');
    expect(score1(null)).toBe('—');
    expect(score1(undefined)).toBe('—');
  });

  it('nf formats integers with the app locale and dashes null', () => {
    expect(nf(1234)).toBe(Number(1234).toLocaleString('en-GB'));
    expect(nf(null)).toBe('—');
  });

  it('signed1 prefixes positive gaps with a plus', () => {
    expect(signed1(0.5)).toBe('+0.5');
    expect(signed1(-0.5)).toBe('-0.5');
    expect(signed1(0)).toBe('0.0');
  });

  it('signed1 shows a dash for null/undefined instead of throwing', () => {
    expect(signed1(null)).toBe('—');
    expect(signed1(undefined)).toBe('—');
  });
});
