import { render, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Capture the props EvaluateHeader hands to CountdownTimer.
const captured = vi.hoisted(() => ({ calls: [] }));
vi.mock('./CountdownTimer.jsx', () => ({
  default: (props) => {
    captured.calls.push(props);
    return null;
  },
}));
vi.mock('./EvaluationStatus.jsx', () => ({ default: () => null }));
vi.mock('./ReEvaluateCard.jsx', () => ({ default: () => null }));
vi.mock('../../../components/terminal/index.js', () => ({ TermHeader: () => null }));
vi.mock('../../../constants.js', () => ({
  ACTIVE_PROVIDER_KEY: 'active-provider',
  DEFAULT_TIME_LIMIT_S: 3600,
  DEFAULT_MAX_SUBAGENTS: 5,
  LOCAL_API_PROVIDERS: new Set(['ollama', 'llamacpp', 'omlx']),
  providerKey: (p, k) => `${p}-${k}`,
}));

import EvaluateScreen from './EvaluateScreen.jsx';

const baseContext = { selectedProject: null, projectInfo: null, jobProjectInfo: null };
const baseActions = {
  onStart: vi.fn(), onDismiss: vi.fn(), onCancel: vi.fn(),
  onGoToProjects: vi.fn(), onGoToSettings: vi.fn(),
};

function renderWithJob(job) {
  return render(
    <EvaluateScreen
      evaluation={{ job, jobError: null, liveViolations: [] }}
      context={baseContext}
      actions={baseActions}
    />,
  );
}

describe('EvaluateHeader -> CountdownTimer wiring', () => {
  beforeEach(() => {
    captured.calls.length = 0;
    localStorage.clear();
    cleanup();
  });

  it('passes a terminal phase when the job status is terminal', () => {
    // job.phase is never terminal (the CLI leaves it at "scoring"), so the
    // countdown must key off status once the run ends; before this fix a
    // finished run kept a red 0:00 pinned in the header forever.
    renderWithJob({
      status: 'done', phase: 'scoring',
      deadlineAt: '2026-07-27T10:00:00+00:00', timeLimitS: 600,
    });
    expect(captured.calls.at(-1).phase).toBe('done');
  });

  it('prefers the running job own budget over the active-provider settings', () => {
    // The snapshot now carries timeLimitS. Reading localStorage instead
    // meant switching provider/limit mid-run changed or hid the countdown
    // of an already-running scan.
    localStorage.setItem('active-provider', 'claude');
    localStorage.setItem('claude-time-limit', '1200');
    renderWithJob({
      status: 'running', phase: 'analyzing',
      deadlineAt: '2026-07-27T10:00:00+00:00', timeLimitS: 300,
    });
    expect(captured.calls.at(-1).budgetSeconds).toBe(300);
  });

  it('job budget 0 (unlimited) wins over a limited settings value', () => {
    localStorage.setItem('active-provider', 'claude');
    localStorage.setItem('claude-time-limit', '600');
    renderWithJob({ status: 'running', phase: 'analyzing', deadlineAt: null, timeLimitS: 0 });
    expect(captured.calls.at(-1).budgetSeconds).toBe(0);
  });

  it('falls back to settings when the job carries no budget', () => {
    localStorage.setItem('active-provider', 'claude');
    localStorage.setItem('claude-time-limit', '900');
    renderWithJob({ status: 'running', phase: 'analyzing', deadlineAt: null });
    expect(captured.calls.at(-1).budgetSeconds).toBe(900);
  });
});
