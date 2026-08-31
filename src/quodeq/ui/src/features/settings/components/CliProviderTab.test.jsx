import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

  it('flags an invalid command override on blur with the server reason', async () => {
    fakeApi.checkCmdPath = vi.fn().mockResolvedValue({
      ok: false,
      error: "'claude-v' was not found or is not executable",
    });
    const Wrapper = makeWrapper();
    const state = { model: 'sonnet', 'cmd-path': 'claude-v' };
    render(
      <Wrapper>
        <CliProviderTab providerId="claude" state={state} update={() => {}} />
      </Wrapper>,
    );

    fireEvent.blur(screen.getByLabelText('Command'));

    await waitFor(() => {
      expect(screen.getByText(/was not found or is not executable/)).toBeTruthy();
    });
    expect(fakeApi.checkCmdPath).toHaveBeenCalledWith('claude', 'claude-v');
  });

  it('clears the override error once the value validates', async () => {
    fakeApi.checkCmdPath = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, error: "'claude-x' was not found or is not executable" })
      .mockResolvedValueOnce({ ok: true, error: null });
    const Wrapper = makeWrapper();
    function Host() {
      const [state, setState] = React.useState({ model: 'sonnet', 'cmd-path': 'claude-x' });
      return (
        <CliProviderTab
          providerId="claude"
          state={state}
          update={(k, v) => setState((s) => ({ ...s, [k]: v }))}
        />
      );
    }
    render(
      <Wrapper>
        <Host />
      </Wrapper>,
    );

    const input = screen.getByLabelText('Command');
    fireEvent.blur(input);
    await waitFor(() => {
      expect(screen.getByText(/was not found/)).toBeTruthy();
    });

    fireEvent.change(input, { target: { value: 'claude-api' } });
    fireEvent.blur(input);
    await waitFor(() => {
      expect(screen.queryByText(/was not found/)).toBeNull();
    });
  });

  it('does not call the check for an empty or provider-default override', () => {
    fakeApi.checkCmdPath = vi.fn();
    const Wrapper = makeWrapper();
    const state = { model: 'sonnet', 'cmd-path': 'claude' };
    render(
      <Wrapper>
        <CliProviderTab providerId="claude" state={state} update={() => {}} />
      </Wrapper>,
    );

    fireEvent.blur(screen.getByLabelText('Command'));

    expect(fakeApi.checkCmdPath).not.toHaveBeenCalled();
  });

  it('does not suggest gpt-5-mini for Codex', () => {
    const Wrapper = makeWrapper();
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    render(
      <Wrapper>
        <CliProviderTab providerId="codex" state={state} update={() => {}} />
      </Wrapper>,
    );

    fireEvent.click(screen.getByLabelText('Model help'));

    expect(screen.queryByText('gpt-5-mini')).toBeNull();
    expect(screen.getByText(/leave this blank to use the Codex CLI default/i)).toBeTruthy();
  });
});
