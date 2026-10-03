import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { HydratedReportContent } from './HydratedReportContent.jsx';
import { withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';

// The run page's fix plan prints every violation's reason; /scores/<run>
// defers it, so the pane hydrates all rows (not only critical and major)
// before building.

const ref = { project: 'proj', run: 'r1', dimension: 'security', generation: 1, kind: 'violation', source: 'local' };
const slim = {
  file: 'src/a.py', line: 1, endLine: null, principle: 'P1', title: 'Shell out', severity: 'minor',
  reason: null, snippet: null, context: null, reqRefs: [], detailDeferred: true, detailRef: ref,
};
const dimensions = [{ dimension: 'security', violations: [slim] }];

describe('HydratedReportContent', () => {
  it('hydrates every row when severities is null and builds from the hydrated dimensions', async () => {
    const getFindingDetail = vi.fn(async () => [{ ...slim, detailRef: undefined, detailDeferred: false, reason: 'Untrusted input' }]);
    const markdownRef = { current: null };
    const build = (dims) => dims.flatMap((d) => d.violations.map((v) => `- ${v.title}: ${v.reason || 'pending'}`)).join('\n');
    render(
      <HydratedReportContent dimensions={dimensions} severities={null} build={build} markdownRef={markdownRef} />,
      { wrapper: withStableQueryApi({ getFindingDetail }) },
    );
    await waitFor(() => expect(markdownRef.current).toContain('Untrusted input'));
    expect(screen.getByText(/Untrusted input/)).toBeInTheDocument();
    expect(getFindingDetail.mock.calls[0][1]).toMatchObject({ run: 'r1', kind: 'violation', dimension: 'security' });
  });

  it('leaves a minor row alone under the report severities', () => {
    const getFindingDetail = vi.fn();
    const build = (dims) => String(dims[0].violations[0].detailDeferred);
    render(<HydratedReportContent dimensions={dimensions} build={build} />, { wrapper: withStableQueryApi({ getFindingDetail }) });
    expect(screen.getByText('true')).toBeInTheDocument();
    expect(getFindingDetail).not.toHaveBeenCalled();
  });
});
