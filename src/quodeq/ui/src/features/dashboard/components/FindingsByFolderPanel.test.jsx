import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import FindingsByFolderPanel from './FindingsByFolderPanel.jsx';

const v = (file, severity = 'minor') => ({ file, severity, req: 'X-1', title: 't' });

describe('FindingsByFolderPanel', () => {
  it('shows the shared prefix once and each folder below it', () => {
    const dims = [{ dimension: 'a', violations: [v('src/main/app/Views/A.swift', 'major'), v('src/main/lib/Views/B.swift')] }];
    render(<FindingsByFolderPanel dimensions={dims} />);
    expect(screen.getByText('IN src/main/ · CLICK TO OPEN')).toBeInTheDocument();
    const rows = screen.getAllByRole('row');
    expect(rows[0]).toHaveTextContent('app/Views/');
    expect(rows[1]).toHaveTextContent('lib/Views/');
  });

  it('keeps two folders with the same last names apart', () => {
    const dims = [{ dimension: 'a', violations: [v('x/one/Article/Views/A.swift'), v('y/two/Article/Views/B.swift')] }];
    render(<FindingsByFolderPanel dimensions={dims} />);
    expect(screen.getAllByRole('row')).toHaveLength(2);
    expect(screen.getByText('2 folders · 2 files with findings')).toBeInTheDocument();
  });

  it('opens a folder with its full path', () => {
    const onFolderClick = vi.fn();
    const dims = [{ dimension: 'a', violations: [v('src/x/a.py'), v('src/y/b.py')] }];
    render(<FindingsByFolderPanel dimensions={dims} onFolderClick={onFolderClick} />);
    fireEvent.click(screen.getAllByRole('row')[0]);
    expect(onFolderClick.mock.calls[0][0].dir.startsWith('src/')).toBe(true);
  });
});

describe('FindingsByFolderPanel, beyond the top folders', () => {
  const many = [{ dimension: 'a', violations: Array.from({ length: 7 }, (_, i) => v(`src/m${i}/f.py`)) }];

  it('shows the top five and hands the rest to the Map', () => {
    const onOpenMap = vi.fn();
    render(<FindingsByFolderPanel dimensions={many} onOpenMap={onOpenMap} />);
    expect(screen.getAllByRole('row')).toHaveLength(5);
    fireEvent.click(screen.getByRole('button', { name: /all folders in Map/ }));
    expect(onOpenMap).toHaveBeenCalled();
  });

  it('has no Map link when every folder already shows', () => {
    const few = [{ dimension: 'a', violations: [v('src/x/a.py'), v('src/y/b.py')] }];
    render(<FindingsByFolderPanel dimensions={few} onOpenMap={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /all folders in Map/ })).not.toBeInTheDocument();
  });
});
