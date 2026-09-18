import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';
import CopilotModelSelect, { CopilotModelStatus } from './CopilotModelSelect.jsx';

function renderModels(api, props = {}) {
  return render(
    <>
      <CopilotModelStatus />
      <CopilotModelSelect value="" onChange={() => {}} {...props} />
    </>,
    { wrapper: withStableQueryApi(api) },
  );
}

it('shows account models, shares the query, and hides login instructions on success', async () => {
  const api = { getClientModels: vi.fn().mockResolvedValue({ models: ['auto', 'gpt-test'] }) };
  const onChange = vi.fn();
  renderModels(api, { onChange });
  expect(await screen.findByRole('option', { name: 'gpt-test' })).toBeTruthy();
  expect(screen.queryByText(/separate Quodeq profile/)).toBeNull();
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'gpt-test' } });
  expect(onChange).toHaveBeenCalledWith('gpt-test');
  expect(api.getClientModels).toHaveBeenCalledTimes(1);
  expect(api.getClientModels).toHaveBeenCalledWith('copilot');
});

it('does not show login instructions while the initial request is pending', () => {
  renderModels({ getClientModels: () => new Promise(() => {}) });
  expect(screen.getByRole('combobox')).toBeDisabled();
  expect(screen.getByRole('status')).toBeTruthy();
  expect(screen.queryByText(/separate Quodeq profile/)).toBeNull();
});

it('shows errors and setup instructions, then hides them after a successful retry', async () => {
  const api = { getClientModels: vi.fn()
    .mockRejectedValueOnce(new Error('Authentication required'))
    .mockResolvedValueOnce({ models: ['auto', 'gpt-test'] }) };
  renderModels(api);
  expect(await screen.findByRole('alert')).toHaveTextContent('Authentication required');
  expect(screen.getByText(/separate Quodeq profile/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Retry connection' }));
  expect(await screen.findByRole('option', { name: 'gpt-test' })).toBeTruthy();
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  expect(screen.queryByText(/separate Quodeq profile/)).toBeNull();
});

it('preserves a saved model that is no longer in the account list', async () => {
  const onChange = vi.fn();
  renderModels({ getClientModels: () => Promise.resolve({ models: ['auto', 'gpt-test'] }) },
    { value: 'saved-model', onChange });
  await screen.findByRole('option', { name: 'gpt-test' });
  expect(screen.getByRole('combobox')).toHaveValue('saved-model');
  expect(onChange).not.toHaveBeenCalled();
});

it.each([{ models: [] }, { models: null }, { models: [42] }])(
  'does not hide setup for a malformed or empty discovery response: %j', async (payload) => {
    renderModels({ getClientModels: () => Promise.resolve(payload) });
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText(/separate Quodeq profile/)).toBeTruthy();
  },
);
