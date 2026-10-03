import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import WorkingCopyNote from './WorkingCopyNote.jsx';

describe('WorkingCopyNote', () => {
  it('says where the working copy goes, and change picks another folder', () => {
    const onChange = vi.fn();
    render(<WorkingCopyNote path="~/quodeq/repos/billing" onChange={onChange} />);
    expect(screen.getByText('quodeq keeps a working copy in ~/quodeq/repos/billing')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'change where the working copy goes' }));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: 'use the default' })).toBeNull();
  });

  it('a changed folder offers the default back', () => {
    const onReset = vi.fn();
    render(<WorkingCopyNote path="/Volumes/work/billing" onChange={() => {}} onReset={onReset} />);
    fireEvent.click(screen.getByRole('button', { name: 'use the default' }));
    expect(onReset).toHaveBeenCalledTimes(1);
  });
});
