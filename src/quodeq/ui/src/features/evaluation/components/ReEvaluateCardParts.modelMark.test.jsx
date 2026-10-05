import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { IdentityHeader, RunBar } from './ReEvaluateCardParts.jsx';

const info = { name: 'Spoon-Knife', path: '/u/repos/Spoon-Knife' };
const scope = { isLocal: true, scopePath: null };

function renderHeader(activeModel) {
  render(<IdentityHeader info={info} project="p1" scope={scope} branchLabel={null} scopeValue="/u/repos/Spoon-Knife/ · whole project" activeModel={activeModel} onOpenScopeBrowser={vi.fn()} onGoToSettings={vi.fn()} onGoToProjects={vi.fn()} />);
}

describe('the model cell', () => {
  it('is marked for attention while no model is chosen', () => {
    renderHeader(null);
    const cell = screen.getByRole('button', { name: 'choose model' }).closest('.eval-identity__cell');
    expect(cell).toHaveClass('eval-identity__cell--attention');
  });

  it('is a plain cell once a model is set', () => {
    renderHeader({ provider: 'ollama', model: 'gemma4' });
    const cell = screen.getByRole('button', { name: /gemma4/ }).closest('.eval-identity__cell');
    expect(cell).not.toHaveClass('eval-identity__cell--attention');
  });
});

describe('the run bar', () => {
  const base = { disabled: false, canStart: true, handleScan: vi.fn(), estimates: null, cleanScan: undefined, timeLimitS: 0 };

  it('says a model is missing before anything else', () => {
    render(<RunBar {...base} selectedDims={new Set()} hasModel={false} />);
    expect(screen.getByText('no model selected · choose one to start a scan')).toBeInTheDocument();
    expect(screen.queryByText('pick at least one dimension to start a scan')).toBeNull();
  });

  it('then asks for a dimension', () => {
    render(<RunBar {...base} selectedDims={new Set()} hasModel />);
    expect(screen.getByText('pick at least one dimension to start a scan')).toBeInTheDocument();
  });
});
