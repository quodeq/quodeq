import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const { mockDetect } = vi.hoisted(() => ({ mockDetect: vi.fn() }));
vi.mock('./providerProbes.js', () => ({ runDetection: mockDetect }));

import { useProviderDetection } from './useProviderDetection.js';

describe('useProviderDetection', () => {
  beforeEach(() => mockDetect.mockReset());

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
});
