import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { LlamaCppLogContext } from '../llamacpp-log/LlamaCppLogContext.js';
import LlamaCppTab from './LlamaCppTab.jsx';

const fakeApi = {
  getLlamacppModels: vi.fn(),
  testLlamacppConcurrency: vi.fn(),
  getLlamacppStatus: vi.fn().mockResolvedValue({ running: false }),
};

const stubLog = { open: false, available: false, openLog: vi.fn(), closeLog: vi.fn() };

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={fakeApi}>
          <LlamaCppLogContext.Provider value={stubLog}>{children}</LlamaCppLogContext.Provider>
        </ApiProvider>
      </QueryWrapper>
    );
  };
}

describe('LlamaCppTab', () => {
  beforeEach(() => {
    fakeApi.getLlamacppModels.mockReset();
    fakeApi.testLlamacppConcurrency.mockReset();
  });

  it('shows the loaded model returned by getLlamacppModels', async () => {
    fakeApi.getLlamacppModels.mockResolvedValue([{ name: 'qwen3.gguf' }]);
    const Wrapper = makeWrapper();
    const update = vi.fn();
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    const { container } = render(
      <Wrapper>
        <LlamaCppTab state={state} update={update} />
      </Wrapper>,
    );
    await waitFor(() => {
      const input = container.querySelector('input[aria-label="Loaded model"]');
      expect(input).toBeTruthy();
      expect(input.value).toBe('qwen3.gguf');
    });
    // The tab mirrors the loaded model into provider state.
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith('model', 'qwen3.gguf');
    });
  });

  it('shows the models error when getLlamacppModels rejects', async () => {
    fakeApi.getLlamacppModels.mockRejectedValue(new Error('no llama-server'));
    const Wrapper = makeWrapper();
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    const { findByText } = render(
      <Wrapper>
        <LlamaCppTab state={state} update={vi.fn()} />
      </Wrapper>,
    );
    expect(await findByText(/couldn(?:'|’)t reach llama-server/i)).toBeTruthy();
  });
});
