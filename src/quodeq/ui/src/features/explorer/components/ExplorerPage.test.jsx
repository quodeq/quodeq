import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import ExplorerPage from './ExplorerPage.jsx';

// The page's own-trend query needs a QueryClient; these render it bare.
vi.mock('./useExplorerTrend.js', () => ({ useExplorerTrend: (_p, _s, trend) => trend ?? [] }));
vi.mock('./explorerDataHooks.js', () => ({
  useExplorerData: () => ({ loading: true, evalData: null, allViolations: [] }),
  buildEvalPrincipalFn: () => () => ({}),
}));

vi.mock('../hooks/useStandardDescriptions.js', () => ({
  useStandardDescriptions: () => ({ standardDescription: '' }),
}));

vi.mock('../../side-pane/index.js', () => ({
  useRegisterWindowSpec: () => {},
  ReportContent: () => null,
}));

describe('ExplorerPage', () => {
  it('shows the shared logo LoadingScreen while data loads, not a text fallback', () => {
    const { container } = render(<ExplorerPage project="demo" dimension="security" />);
    expect(container.querySelector('.loading-screen')).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/loading/i);
  });
});
