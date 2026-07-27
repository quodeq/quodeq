import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

// Stub heavy sub-components used by EvaluateScreen
vi.mock('./EvaluationStatus.jsx', () => ({ default: () => null }));
vi.mock('./ReEvaluateCard.jsx', () => ({ default: () => null }));
vi.mock('./CountdownTimer.jsx', () => ({ default: () => null }));
vi.mock('../../../components/terminal/index.js', () => ({
  TermHeader: () => null,
}));
vi.mock('../../../constants.js', () => ({
  ACTIVE_PROVIDER_KEY: 'active-provider',
  DEFAULT_TIME_LIMIT_S: 3600,
  DEFAULT_MAX_SUBAGENTS: 5,
  LOCAL_API_PROVIDERS: new Set(['ollama', 'llamacpp', 'omlx']),
  providerKey: (p, k) => `${p}-${k}`,
}));

import EvaluateScreen, { readBudgetSeconds } from './EvaluateScreen.jsx';

const baseEvaluation = { job: null, jobError: null, liveViolations: [] };
const baseContext = { selectedProject: null, projectInfo: null, jobProjectInfo: null };
const baseActions = {
  onStart: vi.fn(),
  onDismiss: vi.fn(),
  onCancel: vi.fn(),
  onGoToProjects: vi.fn(),
  onGoToSettings: vi.fn(),
};

describe('ErrorToast accessibility', () => {
  it('dismiss control is a <button> element, not a <div>', () => {
    render(
      <EvaluateScreen
        evaluation={{ ...baseEvaluation, jobError: 'Something went wrong' }}
        context={baseContext}
        actions={baseActions}
      />
    );
    const toast = document.querySelector('.job-error-toast');
    expect(toast).not.toBeNull();
    expect(toast.tagName).toBe('BUTTON');
  });

  it('clicking the toast hides it (onDismiss callback fires)', () => {
    render(
      <EvaluateScreen
        evaluation={{ ...baseEvaluation, jobError: 'Something went wrong' }}
        context={baseContext}
        actions={baseActions}
      />
    );
    const toast = document.querySelector('.job-error-toast');
    expect(toast).not.toBeNull();
    fireEvent.click(toast);
    // After click the toast should be gone from DOM
    expect(document.querySelector('.job-error-toast')).toBeNull();
  });
});

describe('readBudgetSeconds', () => {
  const storage = (entries) => ({ getItem: (key) => (key in entries ? entries[key] : null) });

  it('treats every local-API provider as unlimited when no limit was ever stored', () => {
    // Settings shows these providers as Unlimited by default and never writes
    // the key until the user edits it, so the header must agree — otherwise it
    // renders a phantom countdown for a run that has no limit at all.
    for (const provider of ['ollama', 'llamacpp', 'omlx']) {
      expect(readBudgetSeconds(storage({ 'active-provider': provider }))).toBe(0);
    }
  });

  it('keeps the CLI default for providers that default to a limit', () => {
    expect(readBudgetSeconds(storage({ 'active-provider': 'claude' }))).toBe(3600);
  });

  it('honours an explicitly stored unlimited value', () => {
    expect(readBudgetSeconds(storage({ 'active-provider': 'claude', 'claude-time-limit': '0' }))).toBe(0);
  });
});
