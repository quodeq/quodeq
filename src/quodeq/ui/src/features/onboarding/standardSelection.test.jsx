import { describe, it, expect } from 'vitest';
import { defaultStandardIds, describeStandards, toggledStandards } from './standardSelection.js';

const DIMS = [
  { id: 'security', name: 'Security' },
  { id: 'maintainability', name: 'Maintainability' },
  { id: 'performance', name: 'Performance' },
];

describe('defaultStandardIds', () => {
  it('prefers a standard with the id default', () => {
    expect(defaultStandardIds([...DIMS, { id: 'default', name: 'quodeq default standard' }])).toEqual(['default']);
  });

  it('otherwise the default is every visible standard', () => {
    expect(defaultStandardIds(DIMS)).toEqual(['security', 'maintainability', 'performance']);
  });

  it('nothing loaded yet is no default', () => {
    expect(defaultStandardIds([])).toEqual([]);
  });
});

describe('describeStandards', () => {
  it('the default standard reads with its own name and dimensions', () => {
    const standards = [{ id: 'default', name: 'quodeq default standard', dimensions: ['security', 'reliability'] }];
    expect(describeStandards(standards, ['default'])).toEqual({ name: 'quodeq default standard', dimensions: ['security', 'reliability'] });
  });

  it('every visible standard reads as the quodeq default standard, listing them', () => {
    expect(describeStandards(DIMS, ['security', 'maintainability', 'performance'])).toEqual({
      name: 'quodeq default standard',
      dimensions: ['security', 'maintainability', 'performance'],
    });
  });

  it('a narrower pick names the picked standards', () => {
    expect(describeStandards(DIMS, ['performance', 'security'])).toEqual({ name: 'Security, Performance', dimensions: [] });
  });
});

describe('toggledStandards', () => {
  it('adds and removes, in the list order', () => {
    expect(toggledStandards(DIMS, ['performance'], 'security')).toEqual(['security', 'performance']);
    expect(toggledStandards(DIMS, ['security', 'performance'], 'security')).toEqual(['performance']);
  });

  it('never empties the pick', () => {
    expect(toggledStandards(DIMS, ['security'], 'security')).toEqual(['security']);
  });
});
