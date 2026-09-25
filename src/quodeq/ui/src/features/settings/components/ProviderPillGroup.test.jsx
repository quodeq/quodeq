import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ProviderPillGroup } from './ProviderPillGroup.jsx';

const CLIENTS = [
  { id: 'claude', label: 'Claude' },
  { id: 'ollama', label: 'Ollama', installed: false },
];

describe('ProviderPillGroup', () => {
  it('renders one tab per client, marking the active one and the uninstalled ones', () => {
    const { container } = render(<ProviderPillGroup clients={CLIENTS} activeId="claude" onSelect={() => {}} />);
    expect(container.firstChild).toHaveClass('settings-pill-group');
    expect(container.firstChild).toHaveAttribute('role', 'tablist');
    const claude = screen.getByRole('tab', { name: 'Claude' });
    const ollama = screen.getByRole('tab', { name: 'Ollama' });
    expect(claude).toHaveAttribute('aria-selected', 'true');
    expect(claude).toHaveAttribute('aria-disabled', 'false');
    expect(claude).not.toHaveAttribute('title');
    expect(claude.className).toBe('settings-pill settings-pill--active');
    expect(ollama).toHaveAttribute('aria-selected', 'false');
    expect(ollama).toHaveAttribute('aria-disabled', 'true');
    expect(ollama).toHaveAttribute('title');
    expect(ollama.className).toBe('settings-pill settings-pill--disabled');
  });

  it('ignores clicks on an uninstalled client by default', () => {
    const onSelect = vi.fn();
    render(<ProviderPillGroup clients={CLIENTS} activeId="claude" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Ollama' }));
    expect(onSelect).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('tab', { name: 'Claude' }));
    expect(onSelect).toHaveBeenCalledWith('claude');
  });

  it('selects an uninstalled client when selectUninstalled is set', () => {
    const onSelect = vi.fn();
    render(<ProviderPillGroup clients={CLIENTS} activeId="claude" onSelect={onSelect} selectUninstalled />);
    fireEvent.click(screen.getByRole('tab', { name: 'Ollama' }));
    expect(onSelect).toHaveBeenCalledWith('ollama');
  });
});
