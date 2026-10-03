import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useState } from 'react';
import { useFolderPicker } from './useFolderPicker.jsx';

// The modal itself lists directories through the API; a stand-in keeps the
// test on the promise contract.
vi.mock('../../evaluation/components/FolderBrowser.jsx', () => ({
  default: ({ title, onSelect, onClose }) => (
    <div role="dialog" aria-label={title}>
      <button type="button" onClick={() => onSelect('/Users/me/evals.git')}>pick</button>
      <button type="button" onClick={onClose}>dismiss</button>
    </div>
  ),
}));

function Harness() {
  const { browseFolder, picker } = useFolderPicker();
  const [picked, setPicked] = useState('none');
  return (
    <>
      <button type="button" onClick={async () => setPicked(String(await browseFolder()))}>browse</button>
      <output>{picked}</output>
      {picker}
    </>
  );
}

describe('useFolderPicker', () => {
  it('opens the browser and resolves with the confirmed folder', async () => {
    render(<Harness />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'browse' }));
    expect(screen.getByRole('dialog', { name: 'Choose the evaluations repository folder' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'pick' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('/Users/me/evals.git'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('resolves null when the browser is closed without a pick', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'browse' }));
    fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('null'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
