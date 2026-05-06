import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import CliProviderTab from './CliProviderTab.jsx';

const fakeApi = {};

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
  it('renders a free-text model input pre-populated from state', () => {
    const Wrapper = makeWrapper();
    const state = { model: 'sonnet', subagents: '4', 'time-limit-min': '60' };
    const { container } = render(
      <Wrapper>
        <CliProviderTab providerId="claude" state={state} update={() => {}} />
      </Wrapper>,
    );
    const input = container.querySelector('input.settings-model-input[type="text"]');
    expect(input).toBeTruthy();
    expect(input.value).toBe('sonnet');
  });
});
