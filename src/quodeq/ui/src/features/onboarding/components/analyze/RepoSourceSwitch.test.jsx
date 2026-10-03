import { describe, it, expect, vi } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RepoSourceSwitch from './RepoSourceSwitch.jsx';

describe('RepoSourceSwitch', () => {
  it('is a radiogroup that reports the picked source', () => {
    const onChange = vi.fn();
    render(<RepoSourceSwitch value="url" onChange={onChange} />);
    const group = screen.getByRole('radiogroup', { name: 'repository source' });
    expect(within(group).getByRole('radio', { name: 'paste a git url' })).toBeChecked();
    fireEvent.click(within(group).getByRole('radio', { name: 'choose a local folder' }));
    expect(onChange).toHaveBeenCalledWith('folder');
  });

  it('arrow keys move the pick, like native radios', () => {
    const onChange = vi.fn();
    render(<RepoSourceSwitch value="url" onChange={onChange} />);
    const url = screen.getByRole('radio', { name: 'paste a git url' });
    expect(url).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('radio', { name: 'choose a local folder' })).toHaveAttribute('tabindex', '-1');
    fireEvent.keyDown(url, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('folder');
  });

  it('takes its own labels', () => {
    render(<RepoSourceSwitch value="folder" onChange={() => {}} labels={{ url: 'git url', folder: 'folder' }} />);
    expect(screen.getByRole('radio', { name: 'folder' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'git url' })).not.toBeChecked();
  });
});
