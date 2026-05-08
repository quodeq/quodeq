import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import CloneTargetStep from './CloneTargetStep.jsx';

beforeEach(() => {
  localStorage.clear();
});

describe('CloneTargetStep', () => {
  it('pre-fills last clone root from localStorage', () => {
    localStorage.setItem('quodeq.lastCloneRoot', '/Users/v/code');
    render(<CloneTargetStep repoUrl="https://x/y.git" onSubmit={vi.fn()} onBack={vi.fn()} />);
    expect(screen.getByLabelText(/clone destination/i)).toHaveValue('/Users/v/code');
  });

  it('falls back to ~ when no localStorage value', () => {
    render(<CloneTargetStep repoUrl="https://x/y.git" onSubmit={vi.fn()} onBack={vi.fn()} />);
    expect(screen.getByLabelText(/clone destination/i)).toHaveValue('~');
  });

  it('submitting calls onSubmit with cloneDest and ephemeral=false', () => {
    const onSubmit = vi.fn();
    render(<CloneTargetStep repoUrl="https://x/y.git" onSubmit={onSubmit} onBack={vi.fn()} />);
    const input = screen.getByLabelText(/clone destination/i);
    fireEvent.change(input, { target: { value: '/tmp/code' } });
    fireEvent.click(screen.getByRole('button', { name: /clone and scan/i }));
    expect(onSubmit).toHaveBeenCalledWith({ cloneDest: '/tmp/code', ephemeral: false });
  });

  it('clicking the ephemeral link calls onSubmit with ephemeral=true', () => {
    const onSubmit = vi.fn();
    render(<CloneTargetStep repoUrl="https://x/y.git" onSubmit={onSubmit} onBack={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /just run one evaluation/i }));
    expect(onSubmit).toHaveBeenCalledWith({ cloneDest: null, ephemeral: true });
  });

  it('back button calls onBack', () => {
    const onBack = vi.fn();
    render(<CloneTargetStep repoUrl="https://x/y.git" onSubmit={vi.fn()} onBack={onBack} />);
    fireEvent.click(screen.getByRole('button', { name: /back/i }));
    expect(onBack).toHaveBeenCalled();
  });
});
