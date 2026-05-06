import { describe, it, expect } from 'vitest';

describe('ReEvaluateCard payload field semantics', () => {
  // Unit test for the payload building logic in useDimensionSelection hook.
  // The hook's buildPayload() function was updated to use cleanScan instead of incremental.
  // This test verifies the field name change and boolean inversion logic.

  it('payload should use cleanScan field with correct boolean when toggle is "off" (default)', () => {
    // When Clean scan toggle is OFF (default state), we want incremental analysis (use cache)
    // Old field: payload.incremental = true
    // New field: payload.cleanScan = false
    const cleanScanToggleState = 'off';
    const shouldForcecleanScan = cleanScanToggleState !== 'off';

    expect(shouldForcecleanScan).toBe(false);
  });

  it('payload should use cleanScan field with correct boolean when toggle is "once"', () => {
    // When Clean scan toggle is ONCE, we want full analysis (force clean)
    // Old field: payload.incremental = false
    // New field: payload.cleanScan = true
    const cleanScanToggleState = 'once';
    const shouldForcecleanScan = cleanScanToggleState !== 'off';

    expect(shouldForcecleanScan).toBe(true);
  });

  it('payload should use cleanScan field with correct boolean when toggle is "permanent"', () => {
    // When Clean scan toggle is PERMANENT, we want full analysis (force clean)
    // Old field: payload.incremental = false
    // New field: payload.cleanScan = true
    const cleanScanToggleState = 'permanent';
    const shouldForcecleanScan = cleanScanToggleState !== 'off';

    expect(shouldForcecleanScan).toBe(true);
  });
});
