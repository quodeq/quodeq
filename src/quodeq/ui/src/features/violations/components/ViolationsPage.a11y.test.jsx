/**
 * Accessibility test for ViolationsPage.
 * 6146: the restore-error banner appears without the user asking for it, so
 * it has to announce itself (role="alert"). The page state hook is mocked so
 * the banner can be forced without driving a failing restore mutation.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ViolationsPage from './ViolationsPage.jsx';

const RESTORE_ERROR = 'Restore failed: findings file is read-only';

const pageState = {
  dismissed: [],
  handleRestore: vi.fn(), handleRestoreAll: vi.fn(),
  handleDelete: vi.fn(), handleDeleteAll: vi.fn(),
  restoreError: RESTORE_ERROR,
  visibleDimensions: [],
  summary: { totalViolations: 0, severity: {} },
  topFilesCount: 0,
  uniquePrinciples: 0,
  fileCurrentPath: '',
  setFileCurrentPath: vi.fn(),
};

vi.mock('../hooks/useViolationsPageState.js', () => ({
  useViolationsPageState: () => pageState,
}));

const DATA = {
  accumulatedDimensions: [{ dimension: 'security', violations: [], compliance: [] }],
  selectedProject: 'p1',
  projects: [{ id: 'p1', name: 'p1' }],
  projectsLoaded: true,
  projectName: 'p1',
  loading: false,
  isFetching: false,
  dismissRefreshKey: 0,
  selectedSource: 'local',
};

describe('ViolationsPage restore-error banner (6146)', () => {
  it('announces the banner through role="alert"', () => {
    render(<ViolationsPage data={DATA} callbacks={{}} />);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent(RESTORE_ERROR);
    expect(alert).toHaveClass('error-banner');
  });
});
