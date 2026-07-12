import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import ExplorerPage from './ExplorerPage.jsx';

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
