import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import FindingsByFolderPanel from './FindingsByFolderPanel.jsx';

const v = (file, severity = 'minor') => ({ file, severity, req: 'X-1', title: 't' });

describe('FindingsByFolderPanel', () => {
  it('shows the shared prefix once and each folder below it', () => {
    const dims = [{ dimension: 'a', violations: [v('src/main/app/Views/A.swift', 'major'), v('src/main/lib/Views/B.swift')] }];
    render(<FindingsByFolderPanel dimensions={dims} />);
    expect(screen.getByText(/IN src\/main\//)).toBeInTheDocument();
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
    expect(onFolderClick).toHaveBeenCalledWith(expect.objectContaining({ dir: expect.stringMatching(/^src\//) }));
  });
});
