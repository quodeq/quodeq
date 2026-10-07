import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider } from '../../side-pane/SidePaneProvider.jsx';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { useExplorerPageSpecs } from './useExplorerPageSpecs.jsx';
import { withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';

// A finished run's eval defers each finding's reason and snippet. The
// dimension page's report and fix plan print them, so both panes fetch the
// rows before building, the way the run page's panes do.

const ref = { project: 'proj', run: 'r1', dimension: 'security', kind: 'violation', source: 'local' };
const slim = {
  file: 'src/a.py', line: 1, endLine: null, principle: 'P1', title: 'Shell out', severity: 'critical',
  reason: null, snippet: null, context: null, reqRefs: [], detailDeferred: true, detailRef: ref,
};
const evalData = { dimension: 'security', violations: [slim], compliance: [] };

function Page() {
  useExplorerPageSpecs({
    evalData, principleGrades: [], allViolations: [slim], overallGrade: { score: 6, grade: 'Fair' },
    activeDateLabel: '2026-10-07', activeRunId: 'r1',
  });
  return null;
}

function Dock() {
  const { windows, getRegisteredSpec, addWindow } = useSidePane();
  return (
    <div>
      <button data-testid="open-report" onClick={() => addWindow(getRegisteredSpec('report'))}>report</button>
      <button data-testid="open-plan" onClick={() => addWindow(getRegisteredSpec('fixplan'))}>plan</button>
      {windows.map((w) => <section key={w.id} data-testid={w.type}>{w.render()}</section>)}
    </div>
  );
}

function mount(getFindingDetail) {
  return render(
    <SidePaneProvider>
      <Page />
      <Dock />
    </SidePaneProvider>,
    { wrapper: withStableQueryApi({ getFindingDetail }) },
  );
}

describe('useExplorerPageSpecs', () => {
  it('the fix plan prints the reason and code the eval deferred', async () => {
    const getFindingDetail = vi.fn(async () => [{ ...slim, detailRef: undefined, detailDeferred: false, reason: 'Untrusted input reaches a shell', snippet: 'os.system(x)' }]);
    mount(getFindingDetail);
    fireEvent.click(screen.getByTestId('open-plan'));
    await waitFor(() => expect(screen.getByTestId('fixplan')).toHaveTextContent('Untrusted input reaches a shell'));
    expect(screen.getByTestId('fixplan')).toHaveTextContent('os.system(x)');
    expect(getFindingDetail.mock.calls[0][1]).toMatchObject({ run: 'r1', kind: 'violation', dimension: 'security' });
  });

  it('the report prints the reason of a critical finding the eval deferred', async () => {
    const getFindingDetail = vi.fn(async () => [{ ...slim, detailRef: undefined, detailDeferred: false, reason: 'Untrusted input reaches a shell' }]);
    mount(getFindingDetail);
    fireEvent.click(screen.getByTestId('open-report'));
    await waitFor(() => expect(screen.getByTestId('report')).toHaveTextContent('Untrusted input reaches a shell'));
  });
});
