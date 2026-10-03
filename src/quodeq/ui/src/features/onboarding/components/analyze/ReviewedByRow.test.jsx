import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ReviewedByRow from './ReviewedByRow.jsx';

vi.mock('../../../../api/index.js', () => ({ getProviderConfigs: vi.fn(async () => ({})) }));
vi.mock('../../../settings/components/ProviderTabs.jsx', () => ({
  default: () => <div data-testid="provider-tabs-stub" />,
}));

function provider(over = {}) {
  return {
    status: 'detected', label: 'Claude Code', model: null, configured: false,
    drawerOpen: false, openDrawer: vi.fn(), closeDrawer: vi.fn(), ...over,
  };
}

describe('ReviewedByRow', () => {
  it('while detecting it says it is looking', () => {
    render(<ReviewedByRow provider={provider({ status: 'detecting', label: null })} />);
    expect(screen.getByText('looking for a model on this machine…')).toBeInTheDocument();
  });

  it('a detected provider without a model asks for one, and choose a model opens its tab', () => {
    const p = provider({ chooseModel: vi.fn() });
    render(<ReviewedByRow provider={p} />);
    expect(screen.getByText('Claude Code')).toBeInTheDocument();
    expect(screen.getByText('found · choose a model')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'choose a model' }));
    expect(p.chooseModel).toHaveBeenCalledTimes(1);
    expect(p.openDrawer).not.toHaveBeenCalled();
  });

  it('a detected provider with a model is named with it, and change opens the drawer', () => {
    const p = provider({ model: 'claude-sonnet-5-5' });
    render(<ReviewedByRow provider={p} />);
    expect(screen.getByText('Claude Code')).toBeInTheDocument();
    expect(screen.getByText('claude-sonnet-5-5')).toBeInTheDocument();
    expect(screen.queryByText('found · choose a model')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'change the reviewer' }));
    expect(p.openDrawer).toHaveBeenCalledTimes(1);
  });

  it('a configured provider is named without a found tag', () => {
    render(<ReviewedByRow provider={provider({ status: 'none', configured: true, model: 'gpt-5' , label: 'Codex CLI' })} />);
    expect(screen.getByText('Codex CLI')).toBeInTheDocument();
    expect(screen.queryByText(/found ·/)).toBeNull();
    expect(screen.queryByText('no model found on this machine')).toBeNull();
  });

  it.each(['none', 'error'])('%s offers set one up', (status) => {
    const p = provider({ status, label: null });
    render(<ReviewedByRow provider={p} />);
    expect(screen.getByText('no model found on this machine')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'set one up' }));
    expect(p.openDrawer).toHaveBeenCalledTimes(1);
  });

  it('the open drawer shows the provider tabs and done closes it', () => {
    const p = provider({ drawerOpen: true });
    render(<ReviewedByRow provider={p} />);
    expect(screen.getByTestId('provider-tabs-stub')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'done' }));
    expect(p.closeDrawer).toHaveBeenCalledTimes(1);
  });
});
