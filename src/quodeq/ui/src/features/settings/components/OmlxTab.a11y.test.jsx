import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import OmlxTab from './OmlxTab.jsx';

function makeWrapper(fakeApi) {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryWrapper>
    );
  };
}

// #7338 - the model picker (a <select> when models are known, an <input>
// otherwise) has no accessible name; both need aria-labelledby pointing at
// the shared visible "Model" label.
describe('OmlxTab model picker a11y', () => {
  it('gives the model select an accessible name when models are available', async () => {
    const fakeApi = {
      getOmlxModels: vi.fn().mockResolvedValue([{ name: 'mlx-community/gemma-3-4b-it-4bit' }]),
      testOmlxConcurrency: vi.fn(),
      getOmlxStatus: vi.fn().mockResolvedValue({ running: false }),
    };
    const Wrapper = makeWrapper(fakeApi);
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    render(
      <Wrapper>
        <OmlxTab state={state} update={vi.fn()} />
      </Wrapper>,
    );
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /model/i })).toBeInTheDocument();
    });
  });

  it('gives the model text input an accessible name when no models are available', async () => {
    const fakeApi = {
      getOmlxModels: vi.fn().mockResolvedValue([]),
      testOmlxConcurrency: vi.fn(),
      getOmlxStatus: vi.fn().mockResolvedValue({ running: false }),
    };
    const Wrapper = makeWrapper(fakeApi);
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    render(
      <Wrapper>
        <OmlxTab state={state} update={vi.fn()} />
      </Wrapper>,
    );
    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /model/i })).toBeInTheDocument();
    });
  });
});
