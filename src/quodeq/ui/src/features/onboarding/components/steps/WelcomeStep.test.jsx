import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import WelcomeStep from './WelcomeStep.jsx';

const FRESH = { connected: false, host: null, hasLocalProjects: false, fromSettings: false };

function renderWelcome(adaptation = {}, handlers = {}) {
  const props = {
    onStart: vi.fn(), onConnect: vi.fn(), onImport: vi.fn(), onSkip: vi.fn(), onGoToRepositories: vi.fn(),
    ...handlers,
  };
  render(<WelcomeStep {...props} adaptation={{ ...FRESH, ...adaptation }} />);
  return props;
}

describe('WelcomeStep', () => {
  it('shows how it works and the two paths, start opens analyze, connect opens connect', () => {
    const onStart = vi.fn(); const onConnect = vi.fn();
    render(<WelcomeStep onStart={onStart} onConnect={onConnect} onSkip={() => {}} onGoToRepositories={() => {}} adaptation={FRESH} />);
    expect(screen.getByText('how quodeq works')).toBeInTheDocument();
    expect(screen.getByText('scan')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'start' })); expect(onStart).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'connect' })); expect(onConnect).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'skip for now' })).toBeInTheDocument();
  });

  it('numbers the three rows and titles both paths', () => {
    renderWelcome();
    expect(screen.getAllByText(/^0[123]$/).map((n) => n.textContent)).toEqual(['01', '02', '03']);
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      expect.stringContaining('scan'), expect.stringContaining('review'), expect.stringContaining('score'),
    ]);
    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual(['A repository', 'An evaluations repository']);
  });

  it('skip for now calls onSkip', () => {
    const { onSkip } = renderWelcome();
    fireEvent.click(screen.getByRole('button', { name: 'skip for now' }));
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it('adapts: connected shows the host and go to repositories instead of connect', () => {
    const { onGoToRepositories } = renderWelcome({ connected: true, host: 'github.com/quodeq/evaluations' });
    expect(screen.getByText('your evaluations repository is connected · github.com/quodeq/evaluations')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'connect' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'go to repositories' }));
    expect(onGoToRepositories).toHaveBeenCalledTimes(1);
  });

  it('adapts: local projects turn start into add another', () => {
    const { onStart } = renderWelcome({ hasLocalProjects: true });
    expect(screen.queryByRole('button', { name: 'start' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'add another' }));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it('adapts: opened from Settings hides skip for now', () => {
    renderWelcome({ fromSettings: true });
    expect(screen.queryByRole('button', { name: 'skip for now' })).not.toBeInTheDocument();
  });

  it('the evaluations card offers importing an exported archive', () => {
    const { onImport } = renderWelcome();
    fireEvent.click(screen.getByRole('button', { name: 'or import an exported archive' }));
    expect(onImport).toHaveBeenCalledTimes(1);
  });

  it('hides the import link when no import action is wired', () => {
    renderWelcome({}, { onImport: undefined });
    expect(screen.queryByRole('button', { name: 'or import an exported archive' })).not.toBeInTheDocument();
  });
});
