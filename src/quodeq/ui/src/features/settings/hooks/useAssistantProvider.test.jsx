import { it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAssistantProvider } from './useAssistantProvider.js';

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

it('default mode follows the analysis provider and model live', () => {
  localStorage.setItem('cc-active-provider', 'claude');
  localStorage.setItem('cc-claude-model', 'sonnet');
  const { result } = renderHook(() => useAssistantProvider());
  expect(result.current.mode).toBe('default');
  expect(result.current.activeProvider).toBe('claude');
  expect(result.current.model).toBe('sonnet');
  expect(result.current.followsAnalysis).toBe(true);
});

it('custom mode decouples provider from analysis and persists', () => {
  localStorage.setItem('cc-active-provider', 'claude');
  const { result } = renderHook(() => useAssistantProvider());

  act(() => result.current.setMode('custom'));
  act(() => result.current.setActiveProvider('ollama'));

  expect(result.current.mode).toBe('custom');
  expect(result.current.activeProvider).toBe('ollama');
  expect(result.current.followsAnalysis).toBe(false);
  expect(localStorage.getItem('cc-assistant-mode')).toBe('custom');
  expect(localStorage.getItem('cc-assistant-active-provider')).toBe('ollama');

  // Switching the Analysis provider must NOT move the custom assistant provider.
  act(() => {
    localStorage.setItem('cc-active-provider', 'gemini');
    window.dispatchEvent(new Event('assistant-provider-changed'));
  });
  expect(result.current.activeProvider).toBe('ollama');
});

it('custom model is stored under the assistant model key', () => {
  localStorage.setItem('cc-active-provider', 'claude');
  const { result } = renderHook(() => useAssistantProvider());
  act(() => result.current.setMode('custom'));
  act(() => result.current.setActiveProvider('claude'));
  act(() => result.current.setModel('opus'));
  expect(localStorage.getItem('cc-claude-model-assistant')).toBe('opus');
  expect(result.current.model).toBe('opus');
});

it('switching back to default follows analysis again, live', () => {
  localStorage.setItem('cc-active-provider', 'claude');
  localStorage.setItem('cc-claude-model', 'sonnet');
  const { result } = renderHook(() => useAssistantProvider());
  act(() => result.current.setMode('custom'));
  act(() => result.current.setActiveProvider('ollama'));
  act(() => result.current.setMode('default'));

  expect(result.current.activeProvider).toBe('claude');

  // Change the analysis gate; default mode picks it up on the next re-read.
  act(() => {
    localStorage.setItem('cc-active-provider', 'gemini');
    localStorage.setItem('cc-gemini-model', 'gemini-2.5-pro');
    window.dispatchEvent(new Event('assistant-provider-changed'));
  });
  expect(result.current.activeProvider).toBe('gemini');
  expect(result.current.model).toBe('gemini-2.5-pro');
});

it('default mode updates live when the analysis gate fires the shared event', () => {
  // Regression: changing the analysis model in Settings did not refresh the
  // assistant's Default-mode display until the user toggled Custom↔Default.
  // The analysis gate (useProviderSettings/ProviderTabs) now fires
  // cc-provider-settings-changed; Default mode must re-read on it.
  localStorage.setItem('cc-active-provider', 'ollama');
  localStorage.setItem('cc-ollama-model', 'gemma4:26b');
  const { result } = renderHook(() => useAssistantProvider());
  expect(result.current.model).toBe('gemma4:26b');

  act(() => {
    localStorage.setItem('cc-ollama-model', 'llama3:70b');
    window.dispatchEvent(new Event('cc-provider-settings-changed'));
  });
  expect(result.current.model).toBe('llama3:70b');

  // Changing the analysis PROVIDER via the shared event also propagates.
  act(() => {
    localStorage.setItem('cc-active-provider', 'claude');
    localStorage.setItem('cc-claude-model', 'sonnet');
    window.dispatchEvent(new Event('cc-provider-settings-changed'));
  });
  expect(result.current.activeProvider).toBe('claude');
  expect(result.current.model).toBe('sonnet');
});

it('is enabled by default and setEnabled persists + syncs across instances', () => {
  const a = renderHook(() => useAssistantProvider());
  const b = renderHook(() => useAssistantProvider());
  // On by default — the launcher shows until the user opts out in Settings.
  expect(a.result.current.enabled).toBe(true);

  act(() => a.result.current.setEnabled(false));
  expect(a.result.current.enabled).toBe(false);
  expect(localStorage.getItem('cc-assistant-enabled')).toBe('false');
  // Other instances (drawer provider, launcher) see it live.
  expect(b.result.current.enabled).toBe(false);

  act(() => a.result.current.setEnabled(true));
  expect(a.result.current.enabled).toBe(true);
  expect(b.result.current.enabled).toBe(true);
});

it('an explicit opt-out sticks across new instances', () => {
  localStorage.setItem('cc-assistant-enabled', 'false');
  const { result } = renderHook(() => useAssistantProvider());
  expect(result.current.enabled).toBe(false);
});

it('syncs mode/provider changes across independent hook instances', () => {
  localStorage.setItem('cc-active-provider', 'ollama');
  const a = renderHook(() => useAssistantProvider());
  const b = renderHook(() => useAssistantProvider());

  act(() => a.result.current.setMode('custom'));
  act(() => a.result.current.setActiveProvider('claude'));

  expect(b.result.current.mode).toBe('custom');
  expect(b.result.current.activeProvider).toBe('claude');
});

it('syncs model changes across independent hook instances', () => {
  localStorage.setItem('cc-active-provider', 'claude');
  localStorage.setItem('cc-assistant-mode', 'custom');
  const a = renderHook(() => useAssistantProvider());
  const b = renderHook(() => useAssistantProvider());

  act(() => a.result.current.setModel('opus'));

  expect(b.result.current.model).toBe('opus');
});
