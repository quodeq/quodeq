import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useVisibleStandards } from './useVisibleStandards.js';

vi.mock('../../../api/standards.js', () => ({
  listStandards: vi.fn(),
}));

// eslint-disable-next-line import/first -- must follow the vi.mock hoist above
import { listStandards } from '../../../api/standards.js';

describe('useVisibleStandards (map)', () => {
  it('logs a failed standards fetch instead of swallowing it', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    listStandards.mockRejectedValueOnce(new Error('fetch failed'));

    const { result } = renderHook(() => useVisibleStandards());

    await waitFor(() => {
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining('[useVisibleStandards]'),
        expect.any(Error),
      );
    });
    expect(result.current.standardTypes).toEqual({});
  });
});
