import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

vi.mock('../../hooks/useAppState.js', () => ({ default: () => ({}) }));  // not used directly; see note
vi.mock('../settings/hooks/useAssistantProvider.js', () => ({
  useAssistantProvider: () => ({ activeProvider: 'claude', model: 'sonnet' }),
}));
import { deriveAssistantContext } from './useAssistantContext.js';

it('derives provider/model/project/run/uiState from app + settings', () => {
  const appState = {
    activeTab: 'overview',
    selectedProject: 'selectives',
    selectedRun: 'run-9',
    currentOverviewRun: 'run-9',
    projects: [{ id: 'selectives', name: 'selectives-android', path: '/src/sa' }],
  };
  const gate = { activeProvider: 'claude', model: 'sonnet' };
  const ctx = deriveAssistantContext(appState, gate);
  expect(ctx).toEqual({
    provider: 'claude', model: 'sonnet',
    projectId: 'selectives', runId: 'run-9',
    uiState: {
      view: 'overview', activeTab: 'overview', selectedProject: 'selectives',
      selectedRun: 'run-9', currentOverviewRun: 'run-9',
    },
  });
});

it('includes view for the model even with no run selected', () => {
  const ctx = deriveAssistantContext(
    { activeTab: 'overview', selectedProject: 'selectives', projects: [] },
    { activeProvider: 'claude', model: 'sonnet' },
  );
  expect(ctx.uiState.view).toBe('overview');
  expect(ctx.uiState.currentOverviewRun).toBeUndefined();
});

it('handles no selection gracefully', () => {
  const ctx = deriveAssistantContext({ activeTab: 'projects', projects: [] }, { activeProvider: 'ollama' });
  expect(ctx.projectId).toBeUndefined();
  expect(ctx.runId).toBeUndefined();
  expect(ctx.provider).toBe('ollama');
});
