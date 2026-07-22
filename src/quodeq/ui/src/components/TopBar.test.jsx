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

// Shared projects get read-only assistant sessions server-side (the backend
// roots reads in the shared clone and registers no mutating tools), so the
// launcher is never disabled here. The Evaluate button's own gating lives in
// App.jsx (shouldShowEvaluateButton), not here — TopBar just renders
// whatever onEvaluate it's handed.
describe('TopBar source gating', () => {
  it('renders the assistant launcher when selectedSource is local (default)', () => {
    renderTopBar({ selectedSource: 'local' });
    expect(screen.getByRole('button', { name: /Assistant/i })).toBeInTheDocument();
  });

  it('renders the assistant launcher enabled when selectedSource is shared (read-only session)', () => {
    renderTopBar({ selectedSource: 'shared' });
    const btn = screen.getByRole('button', { name: /^Assistant \(Ctrl\+`\)$/ });
    expect(btn).not.toHaveAttribute('aria-disabled');
  });

  it('defaults to local (assistant shown) when selectedSource is not passed', () => {
    renderTopBar({});
    expect(screen.getByRole('button', { name: /Assistant/i })).toBeInTheDocument();
  });
});
