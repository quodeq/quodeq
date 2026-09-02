import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import OmlxTab from './OmlxTab.jsx';

const fakeApi = {
  getOmlxModels: vi.fn(),
  testOmlxConcurrency: vi.fn(),
  // useOmlxServerStatus depends on this; return offline by default
  getOmlxStatus: vi.fn().mockResolvedValue({ running: false }),
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

describe('OmlxTab', () => {
  beforeEach(() => {
    fakeApi.getOmlxModels.mockReset();
    fakeApi.testOmlxConcurrency.mockReset();
  });

  it('lists omlx models returned by getOmlxModels', async () => {
    fakeApi.getOmlxModels.mockResolvedValue([
      { name: 'mlx-community/gemma-3-4b-it-4bit' },
      { name: 'mlx-community/qwen3-8b' },
    ]);
    const Wrapper = makeWrapper();
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    const { container } = render(
      <Wrapper>
        <OmlxTab state={state} update={vi.fn()} />
      </Wrapper>,
    );
    await waitFor(() => {
      const opts = container.querySelectorAll('select option');
      expect([...opts].some((o) => o.value === 'mlx-community/gemma-3-4b-it-4bit')).toBe(true);
      expect([...opts].some((o) => o.value === 'mlx-community/qwen3-8b')).toBe(true);
    });
  });

  it('shows the models error when getOmlxModels rejects', async () => {
    fakeApi.getOmlxModels.mockRejectedValue(new Error('no omlx'));
    const Wrapper = makeWrapper();
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    const { findByText } = render(
      <Wrapper>
        <OmlxTab state={state} update={vi.fn()} />
      </Wrapper>,
    );
    expect(await findByText(/couldn(?:'|’)t load your omlx models/i)).toBeTruthy();
  });
});
