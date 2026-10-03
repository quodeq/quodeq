import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ByTypeView from './ByTypeView.jsx';
import { DISMISS_SCOPE } from '../violationsVocab.js';

const standard = { id: 'maintainability', principles: [{ name: 'Modifiability', requirements: [{ id: 'M-MDF-1', text: 'No magic literals' }, { id: 'M-MDF-3', text: 'Small functions' }] }] };
const v = (req, file = 'a.py') => ({ req, principle: 'Modifiability', file, line: 1, severity: 'minor' });
const dimensions = [{ dimension: 'maintainability', fromRunId: 'r1', fromDateLabel: '26 Sep', violations: [v('M-MDF-3'), v('M-MDF-3', 'b.py')] }];
const diffsByRun = { r1: { dimensions: { maintainability: { againstRunId: 'r0', types: { perReq: { 'M-MDF-1': [215, 0], 'M-MDF-3': [4, 2] } } } } } };
const props = { dimensions, diffsByRun, standardsByDim: { maintainability: standard }, loading: false };

describe('ByTypeView', () => {
  it('lists open types first and closed types with a badge', () => {
    render(<ByTypeView {...props} onTypeClick={() => {}} onDismissType={() => {}} />);
    const codes = screen.getAllByText(/^M-MDF-\d$/).map((n) => n.textContent);
    expect(codes).toEqual(['M-MDF-3', 'M-MDF-1']);
    expect(screen.getByText('closed')).toBeInTheDocument();
    expect(screen.getByText('-215')).toBeInTheDocument();
    expect(screen.getAllByText('1 open · 1 closed')).toHaveLength(2);
    expect(screen.getByText('Small functions')).toBeInTheDocument();
  });

  it('clicking an open type opens its findings; a closed type is not clickable', () => {
    const onTypeClick = vi.fn();
    render(<ByTypeView {...props} onTypeClick={onTypeClick} />);
    fireEvent.click(screen.getByRole('button', { name: 'Show findings of M-MDF-3' }));
    expect(onTypeClick).toHaveBeenCalledWith(expect.objectContaining({ req: 'M-MDF-3', now: 2 }));
    expect(screen.queryByRole('button', { name: 'Show findings of M-MDF-1' })).toBeNull();
  });

  it('the row menu offers project and principle scopes', () => {
    const onDismissType = vi.fn();
    render(<ByTypeView {...props} onTypeClick={() => {}} onDismissType={onDismissType} />);
    fireEvent.click(screen.getByRole('button', { name: 'Actions for M-MDF-3' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Dismiss all 2 in Modifiability' }));
    expect(onDismissType).toHaveBeenCalledWith(expect.objectContaining({ req: 'M-MDF-3' }), DISMISS_SCOPE.PRINCIPLE);
    expect(screen.queryByRole('button', { name: 'Actions for M-MDF-1' })).toBeNull();
  });

  it('no row menu on a shared project', () => {
    render(<ByTypeView {...props} onTypeClick={() => {}} onDismissType={undefined} />);
    expect(screen.queryByRole('button', { name: /Actions for/ })).toBeNull();
  });

  it('shows a dash for the baseline when the run has none', () => {
    const first = { r1: { dimensions: { maintainability: { againstRunId: null, types: { perReq: {} } } } } };
    render(<ByTypeView {...props} diffsByRun={first} onTypeClick={() => {}} />);
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
    expect(screen.queryByText('closed')).toBeNull();
  });

  it('empty state', () => {
    render(<ByTypeView {...props} dimensions={[]} onTypeClick={() => {}} />);
    expect(screen.getByText('No requirement types with findings.')).toBeInTheDocument();
  });

  it('the principle item counts only that principle\'s findings', () => {
    const mixed = [{ dimension: 'maintainability', fromRunId: 'r1', fromDateLabel: '26 Sep',
      violations: [v('M-MDF-3'), v('M-MDF-3', 'b.py'), { ...v('M-MDF-3', 'c.py'), principle: 'Analyzability' }] }];
    render(<ByTypeView {...props} dimensions={mixed} onTypeClick={() => {}} onDismissType={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Actions for M-MDF-3' }));
    expect(screen.getByRole('menuitem', { name: 'Dismiss all 3 in this project' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Dismiss all 2 in Modifiability' })).toBeInTheDocument();
  });
});
