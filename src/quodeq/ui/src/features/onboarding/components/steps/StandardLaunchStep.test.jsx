import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import StandardLaunchStep from './StandardLaunchStep.jsx';

const noop = () => {};
const standards = [
  { id: 'std-a', name: 'Security 101', description: 'Common security checks' },
  { id: 'std-b', name: 'Code style', description: 'Formatting and naming' },
];
const baseState = (over = {}) => ({
  isFirstProject: true,
  standardIds: new Set(),
  provider: { id: 'codex-cli', model: 'gpt-5.2-codex' },
  projectId: 'uuid-1',
  scan: { total_files: 42 },
  totalTimeLimitS: 600,
  ...over,
});

describe('StandardLaunchStep', () => {
  it('renders radio buttons when isFirstProject=true', () => {
    render(<StandardLaunchStep state={baseState()} actions={{ toggleStandard: noop }} standards={standards} onLaunch={noop} onCancel={noop} onBack={noop} />);
    const radios = screen.getAllByRole('radio');
    expect(radios.length).toBe(2);
  });

  it('renders checkboxes when isFirstProject=false', () => {
    render(<StandardLaunchStep state={baseState({ isFirstProject: false })} actions={{ toggleStandard: noop }} standards={standards} onLaunch={noop} onCancel={noop} onBack={noop} />);
    const boxes = screen.getAllByRole('checkbox');
    expect(boxes.length).toBe(2);
  });

  it('Start evaluation is disabled when no standard is selected', () => {
    render(<StandardLaunchStep state={baseState()} actions={{ toggleStandard: noop }} standards={standards} onLaunch={noop} onCancel={noop} onBack={noop} />);
    expect(screen.getByRole('button', { name: /start evaluation/i })).toBeDisabled();
  });

  it('Start evaluation enabled when one standard is selected; click calls onLaunch', () => {
    const onLaunch = vi.fn();
    render(<StandardLaunchStep state={baseState({ standardIds: new Set(['std-a']) })} actions={{ toggleStandard: noop }} standards={standards} onLaunch={onLaunch} onCancel={noop} onBack={noop} />);
    fireEvent.click(screen.getByRole('button', { name: /start evaluation/i }));
    expect(onLaunch).toHaveBeenCalledWith(['std-a']);
  });

  it('summary strip shows project, provider, model, and selected standards', () => {
    render(<StandardLaunchStep state={baseState({ standardIds: new Set(['std-a']) })} actions={{ toggleStandard: noop }} standards={standards} onLaunch={noop} onCancel={noop} onBack={noop} />);
    expect(screen.getByText(/codex-cli/i)).toBeInTheDocument();
    expect(screen.getByText(/gpt-5.2-codex/i)).toBeInTheDocument();
    expect(screen.getByText(/security 101/i)).toBeInTheDocument();
  });
});
