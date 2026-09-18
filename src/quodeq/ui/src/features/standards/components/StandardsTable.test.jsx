/**
 * Finding #500: downloadStandard rejection must be handled -- no unhandled rejection,
 * error surfaced to user.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Mock the api module before importing the component.
vi.mock('../../../api/index.js', () => ({
  exportStandard: vi.fn(),
}));

import { exportStandard } from '../../../api/index.js';
import StandardsTable from './StandardsTable.jsx';
import { UNKNOWN_STANDARD_TYPE } from '../hooks/useStandards.js';
import { t } from '../../../strings/index.js';

const STANDARD = {
  id: 'my-std',
  name: 'My Standard',
  type: 'custom',
  description: 'desc',
  principleCount: 1,
  requirementCount: 2,
};

const actions = {
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  onDuplicate: vi.fn(),
  isVisible: () => true,
  onToggleVisibility: vi.fn(),
};

describe('StandardsTable customized badge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    exportStandard.mockResolvedValue({ data: {}, fileName: 'test.json' });
  });

  it('still renders a standard filed under the unknown-type fallback bucket instead of dropping it', () => {
    const mystery = { id: 'mystery', name: 'Mystery Standard', type: 'mystery-type', description: '', principleCount: 0, requirementCount: 0 };
    render(
      <StandardsTable
        grouped={{ [UNKNOWN_STANDARD_TYPE]: [mystery] }}
        actions={actions}
        customizedCounts={{}}
      />,
    );
    expect(screen.getByText('Mystery Standard')).toBeInTheDocument();
  });

  it('shows a translated "unknown" pill (not an empty label / "--undefined" class) when a standard has no type at all', () => {
    const noType = { id: 'no-type', name: 'No Type Standard', type: undefined, description: '', principleCount: 0, requirementCount: 0 };
    const { container } = render(
      <StandardsTable
        grouped={{ [UNKNOWN_STANDARD_TYPE]: [noType] }}
        actions={actions}
        customizedCounts={{}}
      />,
    );
    expect(screen.getByText(t('standards.baseUnknown'))).toBeInTheDocument();
    expect(container.querySelector('.standards-base-pill--undefined')).toBeNull();
    expect(container.querySelector('.standards-base-pill--unknown')).toBeInTheDocument();
  });

  it('shows the customized badge when customizedCounts has a nonzero entry for the standard', () => {
    render(
      <StandardsTable
        grouped={{ custom: [STANDARD] }}
        actions={actions}
        customizedCounts={{ 'my-std': 3 }}
      />,
    );
    expect(screen.getByText('3 customized')).toBeInTheDocument();
  });

  it('does not show the badge when customizedCounts has no entry for the standard', () => {
    render(
      <StandardsTable
        grouped={{ custom: [STANDARD] }}
        actions={actions}
        customizedCounts={{}}
      />,
    );
    expect(screen.queryByText(/customized/i)).toBeNull();
  });

  it('does not show the badge when customizedCounts is undefined', () => {
    render(
      <StandardsTable
        grouped={{ custom: [STANDARD] }}
        actions={actions}
      />,
    );
    expect(screen.queryByText(/customized/i)).toBeNull();
  });
});

describe('StandardsTable download error handling (#500)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not produce an unhandled promise rejection when download fails', async () => {
    // Track unhandled rejections.
    const unhandledErrors = [];
    const handler = (event) => {
      unhandledErrors.push(event.reason);
      event.preventDefault();
    };
    window.addEventListener('unhandledrejection', handler);

    exportStandard.mockRejectedValue(new Error('network error'));

    render(<StandardsTable grouped={{ custom: [STANDARD] }} actions={actions} />);

    const downloadBtn = screen.getByRole('button', { name: /download my standard/i });
    fireEvent.click(downloadBtn);

    // Give the promise rejection a chance to propagate.
    await new Promise((r) => setTimeout(r, 50));

    window.removeEventListener('unhandledrejection', handler);

    expect(unhandledErrors).toHaveLength(0);
  });

  it('surfaces the download error to the user when download fails', async () => {
    exportStandard.mockRejectedValue(new Error('network error'));

    render(<StandardsTable grouped={{ custom: [STANDARD] }} actions={actions} />);

    const downloadBtn = screen.getByRole('button', { name: /download my standard/i });
    fireEvent.click(downloadBtn);

    // An error indicator (role="alert", aria-live, or error text) must appear.
    await waitFor(() => {
      const alert = document.querySelector('[role="alert"], [aria-live="assertive"], [aria-live="polite"]');
      const errorText = screen.queryByText(/error|failed|could not/i);
      expect(alert || errorText).not.toBeNull();
    }, { timeout: 2000 });
  });
});
