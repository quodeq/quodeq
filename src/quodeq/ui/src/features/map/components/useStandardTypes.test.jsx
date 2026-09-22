import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useStandardTypes } from './useStandardTypes.js';

vi.mock('../../../api/standards.js', () => ({
  listStandards: vi.fn(),
}));

// eslint-disable-next-line import/first -- must follow the vi.mock hoist above
import { listStandards } from '../../../api/standards.js';

describe('useStandardTypes (map)', () => {
  it('logs a failed standards fetch instead of swallowing it', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    listStandards.mockRejectedValueOnce(new Error('fetch failed'));

    const { result } = renderHook(() => useStandardTypes());

    await waitFor(() => {
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining('[useStandardTypes]'),
        expect.any(Error),
      );
    });
    expect(result.current.standardTypes).toEqual({});
  });
});
