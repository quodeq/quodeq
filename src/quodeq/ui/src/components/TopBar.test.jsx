import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import TopBar from './TopBar.jsx';
import { SidePaneContext } from '../features/side-pane/SidePaneContext.jsx';
import { AssistantDrawerProvider } from '../features/assistant/AssistantDrawerProvider.jsx';

const sidePaneStub = {
  getRegisteredSpec: () => null,
  hasWindow: () => false,
  addWindow: () => {},
  removeWindow: () => {},
};

function renderTopBar(props) {
  return render(
    <AssistantDrawerProvider>
      <SidePaneContext.Provider value={sidePaneStub}>
        <TopBar {...props} />
      </SidePaneContext.Provider>
    </AssistantDrawerProvider>
  );
}

describe('TopBar mobile project label', () => {
  it('renders a tappable project label that calls onSelectProject', () => {
    const onSelectProject = vi.fn();
    renderTopBar({ projectName: 'my-project', mobileTitle: 'violations', onSelectProject });
    const btn = screen.getByRole('button', { name: 'my-project' });
    fireEvent.click(btn);
    expect(onSelectProject).toHaveBeenCalledTimes(1);
  });

  it('still shows the current page label alongside the project', () => {
    renderTopBar({ projectName: 'my-project', mobileTitle: 'violations', onSelectProject: () => {} });
    expect(screen.getByText('violations')).toBeInTheDocument();
  });

  it('omits the project label when no projectName is given', () => {
    renderTopBar({ mobileTitle: 'violations', onSelectProject: () => {} });
    expect(screen.queryByRole('button', { name: 'my-project' })).toBeNull();
    expect(screen.getByText('violations')).toBeInTheDocument();
  });
});

// Shared projects are read-only: the assistant launcher is disabled with an
// explanatory tooltip since the assistant can take write actions (dismiss/verify).
// The Evaluate button's own gating lives in App.jsx (shouldShowEvaluateButton),
// not here — TopBar just renders whatever onEvaluate it's handed.
describe('TopBar source gating', () => {
  it('renders the assistant launcher when selectedSource is local (default)', () => {
    renderTopBar({ selectedSource: 'local' });
    expect(screen.getByRole('button', { name: /Assistant/i })).toBeInTheDocument();
  });

  it('disables (but keeps) the assistant launcher when selectedSource is shared', () => {
    renderTopBar({ selectedSource: 'shared' });
    const btn = screen.getByRole('button', { name: /assistant is unavailable/i });
    expect(btn).toHaveAttribute('aria-disabled', 'true');
  });

  it('defaults to local (assistant shown) when selectedSource is not passed', () => {
    renderTopBar({});
    expect(screen.getByRole('button', { name: /Assistant/i })).toBeInTheDocument();
  });
});
