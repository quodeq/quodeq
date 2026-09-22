import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const { mockDetect } = vi.hoisted(() => ({ mockDetect: vi.fn() }));
vi.mock('./providerProbes.js', () => ({ runDetection: mockDetect }));

import { useProviderDetection } from './useProviderDetection.js';

// Each test below configures mockDetect's resolved/rejected value directly
// (mockResolvedValue/mockRejectedValue/mockReturnValue), which fully
// overrides the prior test's config -- no shared mutable state to reset.
// A `beforeEach(() => mockDetect.mockReset())` here would be redundant, and
// it also collides with Vitest's unhandled-rejection tracking: resetting a
// mock from inside a hook, right before that same mock is configured to
// reject and driven through a promise chain in the test body, causes the
// already-caught rejection to be misreported as unhandled and fails the
// test even though the hook's `.catch` runs correctly.
describe('useProviderDetection', () => {
  it('returns "detecting" while probes resolve', async () => {
    let resolveProbes;
    mockDetect.mockReturnValue(new Promise((resolve) => { resolveProbes = resolve; }));
    const { result } = renderHook(() => useProviderDetection());
    expect(result.current.status).toBe('detecting');
    expect(result.current.preselection).toBeNull();
    // Resolve so the test's pending promise doesn't keep the act() queue open.
    resolveProbes([]);
  });

  it('ranks Codex CLI above Claude Code when both are detected', async () => {
    mockDetect.mockResolvedValue([
      { id: 'claude-code', classification: 'cli', detected: true, defaultModel: 'sonnet-4.6' },
      { id: 'codex-cli', classification: 'cli', detected: true, defaultModel: 'gpt-5.2-codex' },
      { id: 'ollama', classification: 'local-api', detected: true, defaultModel: 'llama3' },
    ]);
    const { result } = renderHook(() => useProviderDetection());
    await waitFor(() => expect(result.current.status).toBe('detected'));
    expect(result.current.preselection.id).toBe('codex-cli');
  });

  it('falls through to Cloud-with-key when no local provider detected', async () => {
    mockDetect.mockResolvedValue([
      { id: 'codex-cli', classification: 'cli', detected: false },
      { id: 'ollama', classification: 'local-api', detected: false },
      { id: 'openai', classification: 'cloud', detected: true, defaultModel: 'gpt-5.2' },
    ]);
    const { result } = renderHook(() => useProviderDetection());
    await waitFor(() => expect(result.current.status).toBe('detected'));
    expect(result.current.preselection.id).toBe('openai');
  });

  it('returns status "none" with null preselection when nothing is detected', async () => {
    mockDetect.mockResolvedValue([
      { id: 'codex-cli', classification: 'cli', detected: false },
      { id: 'ollama', classification: 'local-api', detected: false },
      { id: 'openai', classification: 'cloud', detected: false },
    ]);
    const { result } = renderHook(() => useProviderDetection());
    await waitFor(() => expect(result.current.status).toBe('none'));
    expect(result.current.preselection).toBeNull();
  });

  it('sets status to error when runDetection rejects, instead of hanging on "detecting"', async () => {
    mockDetect.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useProviderDetection());
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.preselection).toBeNull();
  });
});
