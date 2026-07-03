import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAssistantProvider } from './useAssistantProvider.js';

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

it('defaults to the analysis provider when unset', () => {
  localStorage.setItem('cc-active-provider', 'ollama');
  const { result } = renderHook(() => useAssistantProvider());
  expect(result.current.activeProvider).toBe('ollama');
  expect(result.current.followsAnalysis).toBe(true);
});

it('an explicit assistant provider overrides and decouples', () => {
  localStorage.setItem('cc-active-provider', 'ollama');
  const { result } = renderHook(() => useAssistantProvider());
  act(() => result.current.setActiveProvider('claude'));
  expect(result.current.activeProvider).toBe('claude');
  expect(result.current.followsAnalysis).toBe(false);
  expect(localStorage.getItem('cc-assistant-active-provider')).toBe('claude');
});

it('model defaults to the analysis model then decouples', () => {
  localStorage.setItem('cc-active-provider', 'claude');
  localStorage.setItem('cc-claude-model', 'sonnet');
  const { result } = renderHook(() => useAssistantProvider());
  expect(result.current.model).toBe('sonnet');
  act(() => result.current.setModel('opus'));
  expect(localStorage.getItem('cc-claude-model-assistant')).toBe('opus');
});
