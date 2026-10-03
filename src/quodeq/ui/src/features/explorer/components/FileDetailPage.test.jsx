/**
 * Smoke coverage for FileDetailPage.jsx and the modules it composes
 * (ViolationCard.jsx, FileDetailHeader.jsx, fileDetailWidgets.jsx,
 * useFileDetailFiltering.js, useFileDetailWindowSpecs.js). Covers the mount
 * path and the dismiss hot path: dismissing a violation must remove it from
 * the live list without calling onDismiss again for the same row.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import FileDetailPage from './FileDetailPage.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';
import { withQueryClient, withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';
import { t } from '../../../strings/index.js';
import { useFileDetailWindowSpecs } from './useFileDetailWindowSpecs.jsx';

// The report and fix-plan panes build from the file object they are given;
// it must be the hydrated one (see the deferred-detail cases below).
vi.mock('./useFileDetailWindowSpecs.jsx', async (importOriginal) => {
  const mod = await importOriginal();
  return { ...mod, useFileDetailWindowSpecs: vi.fn(mod.useFileDetailWindowSpecs) };
});

function makeFile(overrides = {}) {
  const violation = {
    file: 'src/app.js', line: 12, endLine: 12, severity: 'major',
    dimension: 'security', principle: 'input-validation',
    title: 'Unvalidated input', reason: 'User input reaches a sink unchecked.',
  };
  return {
    file: 'src/app.js',
    total: 1,
    violationsBySeverity: { critical: [], major: [violation], minor: [] },
    compliance: [],
    dimensionsCount: 1,
    ...overrides,
  };
}

function renderPage(props = {}) {
  return render(
    <SidePaneProvider>
      <FileDetailPage file={makeFile()} runId="run-1" dateLabel="2026-08-01" onDismiss={vi.fn()} {...props} />
    </SidePaneProvider>,
    { wrapper: withQueryClient() },
  );
}

describe('FileDetailPage deferred violation detail', () => {
  const ref = { project: 'proj', asOf: null, dimension: 'security', generation: 1, kind: 'violation' };
  const slim = {
    file: 'src/app.js', line: 12, endLine: 12, severity: 'major', dimension: 'security',
    principle: 'input-validation', title: 'Unvalidated input',
    reason: null, snippet: null, context: null, reqRefs: [], detailDeferred: true, detailRef: ref,
  };
  const full = { ...slim, detailRef: undefined, detailDeferred: false, reason: 'User input reaches a sink unchecked.', snippet: 'sink(input)', reqRefs: [{ label: 'CWE-20' }] };

  it('fetches the detail, shows it, and dismisses with the hydrated item', async () => {
    const getFindingDetail = vi.fn(async () => [full]);
    const onDismiss = vi.fn();
    render(
      <SidePaneProvider>
        <FileDetailPage file={makeFile({ violationsBySeverity: { critical: [], major: [slim], minor: [] } })} runId="run-1" dateLabel="2026-08-01" onDismiss={onDismiss} />
      </SidePaneProvider>,
      { wrapper: withStableQueryApi({ getFindingDetail }) },
    );
    expect(await screen.findByText('User input reaches a sink unchecked.')).toBeInTheDocument();
    expect(getFindingDetail).toHaveBeenCalledWith('proj', { kind: 'violation', dimension: 'security', asOf: null, principle: 'input-validation', pathPrefix: 'src/app.js' });
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(onDismiss.mock.calls[0][0]).toMatchObject({ reason: 'User input reaches a sink unchecked.', snippet: 'sink(input)', reqRefs: [{ label: 'CWE-20' }] });
  });

  it('builds the report and fix plan from the hydrated file', async () => {
    const getFindingDetail = vi.fn(async () => [full]);
    render(
      <SidePaneProvider>
        <FileDetailPage file={makeFile({ violationsBySeverity: { critical: [], major: [slim], minor: [] } })} runId="run-1" dateLabel="2026-08-01" onDismiss={vi.fn()} />
      </SidePaneProvider>,
      { wrapper: withStableQueryApi({ getFindingDetail }) },
    );
    await screen.findByText('User input reaches a sink unchecked.');
    const lastCall = useFileDetailWindowSpecs.mock.calls.at(-1)[0];
    expect(lastCall.file.violationsBySeverity.major[0]).toMatchObject({ reason: 'User input reaches a sink unchecked.', snippet: 'sink(input)' });
  });
});

describe('FileDetailPage', () => {
  it('names the virtualized violations list for assistive tech', () => {
    renderPage();
    expect(screen.getByRole('list', { name: 'Violations' })).toBeInTheDocument();
  });

  it('mounts without crashing and renders the file header + violation', () => {
    expect(() => renderPage()).not.toThrow();
    expect(screen.getByText('src/app.js')).toBeInTheDocument();
    expect(screen.getByText('Unvalidated input')).toBeInTheDocument();
  });

  it('dismissing a violation calls onDismiss once and removes the row from the live list', () => {
    const onDismiss = vi.fn();
    renderPage({ onDismiss });
    const dismissBtn = screen.getByRole('button', { name: /dismiss/i });
    fireEvent.click(dismissBtn);
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Unvalidated input')).not.toBeInTheDocument();
  });

  it('does not render a dismiss control when onDismiss is not provided', () => {
    renderPage({ onDismiss: undefined });
    expect(screen.queryByRole('button', { name: /dismiss/i })).not.toBeInTheDocument();
  });

  it('does not throw when the file object has no dimensionsCount', () => {
    const file = makeFile({ dimensionsCount: undefined });
    expect(() => renderPage({ file })).not.toThrow();
  });

  it('shows 0 dimensions when the file object has no dimensionsCount', () => {
    const file = makeFile({ dimensionsCount: undefined });
    renderPage({ file });
    const label = screen.getByText(t('explorer.dimensionsStat'));
    expect(label.closest('.term-stat').querySelector('.term-stat__value')).toHaveTextContent('0');
  });

  it('severity filter pills narrow the list to the selected severity', () => {
    const file = makeFile({
      violationsBySeverity: {
        critical: [{ file: 'a.js', line: 1, severity: 'critical', title: 'Crit issue' }],
        major: [{ file: 'b.js', line: 2, severity: 'major', title: 'Major issue' }],
        minor: [],
      },
      total: 2,
    });
    renderPage({ file });
    expect(screen.getByText('Crit issue')).toBeInTheDocument();
    expect(screen.getByText('Major issue')).toBeInTheDocument();
    const criticalPill = screen.getAllByRole('button').find((b) => /critical/i.test(b.textContent));
    expect(criticalPill).toBeTruthy();
    fireEvent.click(criticalPill);
    expect(screen.getByText('Crit issue')).toBeInTheDocument();
    expect(screen.queryByText('Major issue')).not.toBeInTheDocument();
  });
});
