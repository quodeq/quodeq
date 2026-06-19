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
