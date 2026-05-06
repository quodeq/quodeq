import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { OllamaLogContext } from '../ollama-log/OllamaLogContext.js';
import OllamaTab from './OllamaTab.jsx';

const fakeApi = {
  getOllamaModels: vi.fn(),
  testOllamaConcurrency: vi.fn(),
  // useOllamaServerStatus depends on this; return offline by default
  getOllamaServerStatus: vi.fn().mockResolvedValue({ status: 'offline' }),
};

const stubOllamaLog = { open: false, openLog: vi.fn(), closeLog: vi.fn() };

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={fakeApi}>
          <OllamaLogContext.Provider value={stubOllamaLog}>{children}</OllamaLogContext.Provider>
        </ApiProvider>
      </QueryWrapper>
    );
  };
}

describe('OllamaTab', () => {
  beforeEach(() => {
    fakeApi.getOllamaModels.mockReset();
    fakeApi.testOllamaConcurrency.mockReset();
  });

  it('lists Ollama models returned by getOllamaModels', async () => {
    fakeApi.getOllamaModels.mockResolvedValue([
      { name: 'llama3.1' },
      { name: 'qwen3' },
    ]);
    const Wrapper = makeWrapper();
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    const { container } = render(
      <Wrapper>
        <OllamaTab state={state} update={vi.fn()} />
      </Wrapper>,
    );
    await waitFor(() => {
      const opts = container.querySelectorAll('select option');
      expect([...opts].some((o) => o.value === 'llama3.1')).toBe(true);
      expect([...opts].some((o) => o.value === 'qwen3')).toBe(true);
    });
  });

  it('shows the models error when getOllamaModels rejects', async () => {
    fakeApi.getOllamaModels.mockRejectedValue(new Error('no ollama'));
    const Wrapper = makeWrapper();
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    const { findByText } = render(
      <Wrapper>
        <OllamaTab state={state} update={vi.fn()} />
      </Wrapper>,
    );
    expect(await findByText(/couldn(?:'|’)t load your Ollama models/i)).toBeTruthy();
  });
});
