import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import AssistantProviderTabs from './AssistantProviderTabs.jsx';

const CLIENTS = [
  { id: 'claude', label: 'Claude', type: 'cli', installed: true },
  { id: 'ollama', label: 'Ollama', type: 'local-api', installed: true },
];

const fakeApi = {
  getAiClients: vi.fn().mockResolvedValue({ clients: CLIENTS }),
  getOllamaModels: vi.fn().mockResolvedValue([{ name: 'gemma4:26b' }]),
  getLlamacppModels: vi.fn().mockResolvedValue([]),
  getOmlxModels: vi.fn().mockResolvedValue([]),
};

const providerConfigs = {
  ollama: { api_base: 'http://localhost:11434' },
  claude: {},
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

async function renderPanel() {
  const Wrapper = makeWrapper();
  let utils;
  await act(async () => {
    utils = render(
      <Wrapper>
        <AssistantProviderTabs providerConfigs={providerConfigs} />
      </Wrapper>,
    );
  });
  return utils;
}

describe('AssistantProviderTabs', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('cc-active-provider', 'claude');
    localStorage.setItem('cc-claude-model', 'sonnet');
    fakeApi.getAiClients.mockClear();
    fakeApi.getOllamaModels.mockClear();
  });
  afterEach(() => localStorage.clear());

  it('default mode hides provider pills and shows the Follows Analysis note', async () => {
    const { container, findByText, queryAllByRole } = await renderPanel();
    // The only tablist is the Default/Custom toggle (2 tabs); no provider pills.
    await waitFor(() => expect(container.querySelectorAll('[role="tablist"]').length).toBe(1));
    expect(queryAllByRole('tab').map((t) => t.textContent)).toEqual(['Default', 'Custom']);
    expect(await findByText(/Follows Analysis/i)).toBeTruthy();
    expect(container.querySelector('select')).toBeNull();
  });

  it('custom mode with a cli provider renders provider pills and a model text input', async () => {
    localStorage.setItem('cc-assistant-mode', 'custom');
    const { container, findByText } = await renderPanel();
    expect(await findByText('Claude')).toBeTruthy();
    expect(await findByText('Ollama')).toBeTruthy();
    // claude is cli → text input, not a select
    const input = container.querySelector('input.settings-model-input');
    expect(input).toBeTruthy();
    expect(container.querySelector('select')).toBeNull();
  });

  it('custom mode with an ollama provider renders a model dropdown', async () => {
    localStorage.setItem('cc-assistant-mode', 'custom');
    localStorage.setItem('cc-assistant-active-provider', 'ollama');
    const { container } = await renderPanel();
    await waitFor(() => {
      const opts = container.querySelectorAll('select option');
      expect([...opts].some((o) => o.value === 'gemma4:26b')).toBe(true);
    });
    expect(fakeApi.getOllamaModels).toHaveBeenCalled();
  });
});
