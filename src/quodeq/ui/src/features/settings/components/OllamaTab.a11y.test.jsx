import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { OllamaLogContext } from '../ollama-log/OllamaLogContext.js';
import OllamaTab from './OllamaTab.jsx';

const fakeApi = {
  getOllamaModels: vi.fn().mockResolvedValue([{ name: 'llama3.1' }]),
  testOllamaConcurrency: vi.fn(),
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

// #6533 - the model <select> has no accessible name; the visible "Model"
// label span needs an id and the select needs aria-labelledby to it.
describe('OllamaTab model select a11y', () => {
  it('gives the model select an accessible name from the visible label', async () => {
    const Wrapper = makeWrapper();
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    render(
      <Wrapper>
        <OllamaTab state={state} update={vi.fn()} />
      </Wrapper>,
    );
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /model/i })).toBeInTheDocument();
    });
  });
});
