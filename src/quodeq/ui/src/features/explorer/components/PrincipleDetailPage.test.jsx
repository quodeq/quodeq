import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider } from '../../side-pane/index.js';
import PrincipleDetailPage from './PrincipleDetailPage.jsx';
import { withQueryClient, withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';

// Pins the eval-principle detail route's dismiss-button gating contract.
// App.jsx's evalprinciple/eval-principle-detail renderer passes onDismiss as
// undefined for shared projects (no mutation route exists on the backend).
// usePrincipleData wraps onDismiss in a stable, always-callable handleDismiss
// (so it never throws when onDismiss is omitted) — but that means naively
// forwarding handleDismiss to EvalViolationCard would keep the dismiss button
// visible regardless of the real onDismiss. PrincipleDetailPage must gate on
// the original onDismiss prop so the button actually vanishes.
const EVAL_PRINCIPAL = {
  principle: 'Input Validation',
  dimension: 'Security',
  project: 'proj',
  runId: 'r1',
  principleData: { violations: [], compliance: [] },
  dimViolations: [{ file: 'a.py', line: 10, severity: 'critical', principle: 'Input Validation' }],
  dimCompliance: [],
  score: '7.0/10',
  grade: 'B',
  dateLabel: '',
};

function renderPage(onDismiss) {
  return render(
    <SidePaneProvider>
      <PrincipleDetailPage evalPrincipal={EVAL_PRINCIPAL} severityFilter={null} onDismiss={onDismiss} />
    </SidePaneProvider>,
    { wrapper: withQueryClient() },
  );
}

describe('PrincipleDetailPage deferred compliance detail', () => {
  it('fetches and shows the detail /scores left out of a compliance card', async () => {
    const ref = { project: 'proj', asOf: null, dimension: 'Security', generation: 1 };
    const slim = {
      file: 'b.py', line: 3, endLine: null, principle: 'Input Validation', title: 'Validated',
      reason: null, snippet: null, context: null, reqRefs: [], detailDeferred: true, detailRef: ref,
    };
    const getComplianceDetail = vi.fn(async () => [{ ...slim, detailRef: undefined, detailDeferred: false, reason: 'Input is checked before use' }]);
    render(
      <SidePaneProvider>
        <PrincipleDetailPage evalPrincipal={{ ...EVAL_PRINCIPAL, dimCompliance: [slim] }} severityFilter={null} onDismiss={vi.fn()} />
      </SidePaneProvider>,
      { wrapper: withStableQueryApi({ getComplianceDetail, getStandard: vi.fn(async () => null) }) },
    );

    expect(await screen.findByText('Input is checked before use')).toBeInTheDocument();
    await waitFor(() => expect(getComplianceDetail).toHaveBeenCalledWith(
      'proj', { dimension: 'Security', asOf: null, principle: 'Input Validation', pathPrefix: 'b.py' },
    ));
  });
});

describe('PrincipleDetailPage dismiss-button gating', () => {
  it('shows the dismiss button when onDismiss is provided (local project)', () => {
    renderPage(vi.fn());
    expect(screen.getByRole('button', { name: /dismiss this finding/i })).toBeInTheDocument();
  });

  it('hides the dismiss button when onDismiss is undefined (shared project)', () => {
    renderPage(undefined);
    expect(screen.queryByRole('button', { name: /dismiss this finding/i })).toBeNull();
  });

  it('names the virtualized violations list for assistive tech', () => {
    renderPage(vi.fn());
    expect(screen.getByRole('list', { name: 'Violations' })).toBeInTheDocument();
  });
});
