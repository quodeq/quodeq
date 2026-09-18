import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

// Stub heavy sub-components used by EvaluateScreen, same as EvaluateScreen.test.jsx.
vi.mock('./EvaluationStatus.jsx', () => ({ default: () => null }));
vi.mock('./ReEvaluateCard.jsx', () => ({ default: () => null }));
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

import EvaluateScreen from './EvaluateScreen.jsx';

const baseEvaluation = { job: null, jobError: null, liveViolations: [] };
const baseContext = { selectedProject: null, projectInfo: null, jobProjectInfo: null };
const baseActions = {
  onStart: vi.fn(),
  onDismiss: vi.fn(),
  onCancel: vi.fn(),
  onGoToProjects: vi.fn(),
  onGoToSettings: vi.fn(),
};

describe('EvaluateScreen error toast a11y', () => {
  it('is announced as an alert so a screen reader user is notified without stumbling onto it', () => {
    render(
      <EvaluateScreen
        evaluation={{ ...baseEvaluation, jobError: 'Something went wrong' }}
        context={baseContext}
        actions={baseActions}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
  });
});
