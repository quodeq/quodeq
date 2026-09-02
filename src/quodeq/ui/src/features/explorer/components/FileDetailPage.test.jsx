/**
 * Smoke coverage for FileDetailPage.jsx, written BEFORE it is split into
 * ViolationCard.jsx, FileDetailHeader.jsx, fileDetailWidgets.jsx,
 * useFileDetailFiltering.js and useFileDetailWindowSpecs.js. Covers the
 * mount path and the dismiss hot path (the brief calls this out explicitly
 * — dismissing a violation must remove it from the live list without
 * calling onDismiss again for the same row).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import FileDetailPage from './FileDetailPage.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

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
  );
}

describe('FileDetailPage', () => {
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
