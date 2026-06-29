import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import TopBar from './TopBar.jsx';
import { SidePaneContext } from '../features/side-pane/SidePaneContext.jsx';

const sidePaneStub = {
  getRegisteredSpec: () => null,
  hasWindow: () => false,
  addWindow: () => {},
  removeWindow: () => {},
};

function renderTopBar(props) {
  return render(
    <SidePaneContext.Provider value={sidePaneStub}>
      <TopBar {...props} />
    </SidePaneContext.Provider>
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
