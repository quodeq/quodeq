import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import CliProviderTab from './CliProviderTab.jsx';

const fakeApi = {
  getKnownModels: vi.fn(),
};

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryWrapper>
    );
  };
}

describe('CliProviderTab', () => {
  beforeEach(() => {
    fakeApi.getKnownModels.mockReset();
  });

  it('fetches known models for the active provider on mount', async () => {
    fakeApi.getKnownModels.mockResolvedValue({
      'cli-foo': [{ id: 'm1', label: 'M1', tier: 'fast' }],
    });
    const Wrapper = makeWrapper();
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    const update = vi.fn();
    const { container } = render(
      <Wrapper>
        <CliProviderTab providerId="cli-foo" state={state} update={update} />
      </Wrapper>,
    );
    await waitFor(() => {
      expect(fakeApi.getKnownModels).toHaveBeenCalled();
    });
    // datalist is populated with M1 (option value="m1")
    await waitFor(() => {
      const datalists = container.querySelectorAll('datalist option');
      expect([...datalists].some((opt) => opt.value === 'm1')).toBe(true);
    });
  });
});
