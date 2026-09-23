import { render, screen, fireEvent } from '@testing-library/react';
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
  it('is announced as an alert so a screen reader user is notified without stumbling onto it, while the dismiss control still reads as a button', () => {
    // role="alert" on the dismiss <button> itself would override its button
    // role for assistive tech. A sibling
    // sr-only alert carries the same text so the message is announced on
    // insertion without taking over the control's semantics.
    render(
      <EvaluateScreen
        evaluation={{ ...baseEvaluation, jobError: 'Something went wrong' }}
        context={baseContext}
        actions={baseActions}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
    expect(screen.getByRole('button', { name: 'Something went wrong' })).toBeInTheDocument();
  });

  it('dismissing via the button still hides the toast (and its alert twin)', () => {
    render(
      <EvaluateScreen
        evaluation={{ ...baseEvaluation, jobError: 'Something went wrong' }}
        context={baseContext}
        actions={baseActions}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Something went wrong' }));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(document.querySelector('.job-error-toast')).toBeNull();
  });
});
