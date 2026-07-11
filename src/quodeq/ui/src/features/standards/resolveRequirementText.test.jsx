import { describe, it, expect } from 'vitest';
import { resolveRequirementText } from './resolveRequirementText.js';

const REQ = {
  id: 'M-ANA-2',
  text: 'Functions MUST NOT exceed {max_lines} lines',
  params: { max_lines: { label: 'Max function lines', type: 'int', default: 50, min: 10, max: 500 } },
};

describe('resolveRequirementText', () => {
  it('renders the default without overrides', () => {
    expect(resolveRequirementText(REQ, undefined)).toBe('Functions MUST NOT exceed 50 lines');
  });

  it('applies a valid override', () => {
    expect(resolveRequirementText(REQ, { max_lines: 60 })).toBe('Functions MUST NOT exceed 60 lines');
  });

  it('falls back to default for out-of-bounds or non-integer overrides', () => {
    expect(resolveRequirementText(REQ, { max_lines: 99999 })).toBe('Functions MUST NOT exceed 50 lines');
    expect(resolveRequirementText(REQ, { max_lines: 'x' })).toBe('Functions MUST NOT exceed 50 lines');
  });

  it('returns text verbatim when no params are declared', () => {
    expect(resolveRequirementText({ id: 'X', text: 'No {placeholders} resolved' }, {}))
      .toBe('No {placeholders} resolved');
  });
});
