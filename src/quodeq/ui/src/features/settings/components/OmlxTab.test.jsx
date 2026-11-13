import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor, fireEvent, screen } from '@testing-library/react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import OmlxTab from './OmlxTab.jsx';
import { findSelectOption } from '../../../test-utils/selectOption.js';

const fakeApi = {
  getOmlxModels: vi.fn(),
  testOmlxConcurrency: vi.fn(),
  // useOmlxServerStatus depends on this; return offline by default
  getOmlxStatus: vi.fn().mockResolvedValue({ running: false }),
  getProviderKeyStatus: vi.fn().mockResolvedValue({ configured: false }),
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
    render(
      <Wrapper>
        <OmlxTab state={state} update={vi.fn()} />
      </Wrapper>,
    );
    expect(await findSelectOption('mlx-community/gemma-3-4b-it-4bit')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'mlx-community/qwen3-8b' })).toBeInTheDocument();
  });

  it('reloads the model list once a saved key has landed', async () => {
    fakeApi.getOmlxModels.mockResolvedValue([]);
    const update = vi.fn(() => Promise.resolve());
    const Wrapper = makeWrapper();
    render(<Wrapper><OmlxTab state={{ model: '' }} update={update} /></Wrapper>);
    await waitFor(() => expect(fakeApi.getOmlxModels).toHaveBeenCalledTimes(1));
    fireEvent.change(await screen.findByLabelText(/api key/i, { selector: 'input' }), { target: { value: 'k' } });
    fireEvent.click(screen.getByRole('button', { name: /save key/i }));
    await waitFor(() => expect(fakeApi.getOmlxModels).toHaveBeenCalledTimes(2));
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
