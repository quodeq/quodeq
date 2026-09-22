import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import AssistantProviderTabs from './AssistantProviderTabs.jsx';

const fakeApi = {
  getAiClients: vi.fn().mockRejectedValue(new Error('clients down')),
  getOllamaModels: vi.fn().mockResolvedValue([]),
  getLlamacppModels: vi.fn().mockResolvedValue([]),
  getOmlxModels: vi.fn().mockResolvedValue([]),
};

const providerConfigs = { claude: {} };

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

// #6374 - the client-list error text is unsolicited and must be announced
// to a screen reader via role="alert", not a plain span.
describe('AssistantProviderTabs client-list error a11y', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('cc-assistant-enabled', 'true');
  });
  afterEach(() => localStorage.clear());

  it('announces the client-list error as an alert', async () => {
    const Wrapper = makeWrapper();
    await act(async () => {
      render(
        <Wrapper>
          <AssistantProviderTabs providerConfigs={providerConfigs} />
        </Wrapper>,
      );
    });
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t load your AI providers/i);
  });
});
