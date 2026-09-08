import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';

const files = [
  { file: 'src/quodeq/api/routes.py', total: 3, critical: 1, major: 0, minor: 2 },
  { file: 'setup.py', total: 1, critical: 0, major: 1, minor: 0 },
];

describe('TopOffendingFilesTable', () => {
  it('splits each path into basename and directory, no directory for root files', () => {
    const { container } = render(<TopOffendingFilesTable files={files} />);
    const names = [...container.querySelectorAll('.offending-file-name')].map((el) => el.textContent);
    const dirs = [...container.querySelectorAll('.offending-file-path')].map((el) => el.textContent);
    expect(names).toEqual(['routes.py', 'setup.py']);
    expect(dirs).toEqual(['src/quodeq/api']);
  });

  it('hands the clicked file object to onFileClick', () => {
    const onFileClick = vi.fn();
    const { container } = render(<TopOffendingFilesTable files={files} onFileClick={onFileClick} />);
    fireEvent.click(container.querySelectorAll('[role="row"]')[1]);
    expect(onFileClick).toHaveBeenCalledWith(files[1]);
  });

  it('renders nothing without files', () => {
    const { container } = render(<TopOffendingFilesTable files={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
