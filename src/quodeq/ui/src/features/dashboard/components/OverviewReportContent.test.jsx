import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { OverviewReportContent, hydrateReportDimensions } from './OverviewReportContent.jsx';
import { REPORT_SEVERITIES } from './HydratedReportContent.jsx';
import { withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';

// The Overview report prints critical and major violations with their
// reason and snippet; /scores defers those, so the report hydrates them
// first and hands the finished Markdown to the pane's copy/download.

const ref = { project: 'proj', asOf: null, dimension: 'security', generation: 1, kind: 'violation' };
const slim = {
  file: 'src/a.py', line: 1, endLine: null, principle: 'P1', title: 'Shell out', severity: 'critical',
  reason: null, snippet: null, context: null, reqRefs: [], detailDeferred: true, detailRef: ref,
};
const minorSlim = { ...slim, file: 'src/z.py', line: 9, title: 'Nit', severity: 'minor' };
const accumulated = { summary: { numericAverage: 7.5, overallGrade: 'B' }, dimensions: [] };
const dimensions = [{ dimension: 'security', overallScore: '7.5', overallGrade: 'B', violations: [slim, minorSlim], compliance: [] }];

describe('hydrateReportDimensions', () => {
  it('replaces each dimension\'s printed violations with its fetched rows and leaves the rest', () => {
    const hydrated = [{ ...slim, reason: 'because', detailDeferred: false }];
    const [dim] = hydrateReportDimensions(dimensions, hydrated, REPORT_SEVERITIES);
    expect(dim.violations[0].reason).toBe('because');
    expect(dim.violations[1]).toBe(minorSlim);
    expect(dim.overallScore).toBe('7.5');
  });

  it('leaves a dimension whose detail has not loaded alone', () => {
    const [dim] = hydrateReportDimensions(dimensions, [slim, minorSlim], REPORT_SEVERITIES);
    expect(dim).toBe(dimensions[0]);
  });
});

describe('OverviewReportContent', () => {
  it('hydrates the critical and major violations, then renders and stores the Markdown', async () => {
    const getFindingDetail = vi.fn(async () => [{ ...slim, detailRef: undefined, detailDeferred: false, reason: 'Untrusted input reaches a shell', snippet: 'os.system(x)' }]);
    const markdownRef = { current: null };
    render(
      <OverviewReportContent accumulated={accumulated} dimensions={dimensions} projectName="proj" extras={{}} markdownRef={markdownRef} />,
      { wrapper: withStableQueryApi({ getFindingDetail }) },
    );
    await waitFor(() => expect(markdownRef.current || '').toContain('Untrusted input reaches a shell'));
    expect(screen.getByText(/Untrusted input reaches a shell/)).toBeInTheDocument();
    // Only the critical/major rows are fetched: the minor one shares the ref
    // but is not printed, so the request scope is the one critical row.
    expect(getFindingDetail).toHaveBeenCalledTimes(1);
    expect(getFindingDetail.mock.calls[0][1]).toMatchObject({ kind: 'violation', dimension: 'security', pathPrefix: 'src/a.py' });
  });
});
