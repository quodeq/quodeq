import { render } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { useEffect } from 'react';

// The setup card keeps per-project state (the seeded selection, "as your
// last run", the user's own picks). A project switch must start a fresh
// card rather than carry one project's selection onto another.
const mounts = vi.hoisted(() => []);
vi.mock('./EvaluationStatus.jsx', () => ({ default: () => null }));
vi.mock('./ReEvaluateCard.jsx', () => ({
  default: function Card({ project }) {
    useEffect(() => { mounts.push(project); }, []); // eslint-disable-line react-hooks/exhaustive-deps -- once per mount
    return null;
  },
}));
vi.mock('../../../components/terminal/index.js', () => ({ TermHeader: () => null }));

import EvaluateScreen from './EvaluateScreen.jsx';

const evaluation = { job: null, jobError: null, liveViolations: [] };
const actions = { onStart: vi.fn(), onDismiss: vi.fn(), onCancel: vi.fn(), onGoToProjects: vi.fn(), onGoToSettings: vi.fn() };
const screenFor = (project) => (
  <EvaluateScreen evaluation={evaluation} context={{ selectedProject: project, projectInfo: null, jobProjectInfo: null }} actions={actions} />
);

describe('EvaluateScreen setup card per project', () => {
  it('starts a fresh setup card when the project changes', () => {
    const { rerender } = render(screenFor('a'));
    rerender(screenFor('a'));
    rerender(screenFor('b'));
    expect(mounts).toEqual(['a', 'b']);
  });
});
