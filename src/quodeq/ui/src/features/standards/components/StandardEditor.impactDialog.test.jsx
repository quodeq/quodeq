/**
 * Tests for StandardEditor's threshold-impact dialog (dry-run preview on save).
 *
 * Split from StandardEditor.test.jsx. Shared fixtures live in
 * _standardEditor.fixtures.js.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// ── module mocks ──────────────────────────────────────────────────────────────

vi.mock('../hooks/useStandardDetail.js', () => ({
  useStandardDetail: vi.fn(),
}));

vi.mock('../hooks/useStandardsOverrides.js', () => ({
  useStandardsOverrides: vi.fn(),
}));

vi.mock('../../../hooks/useAppState.js', () => ({
  useAppState: vi.fn(),
}));

// ── imports after mocks ───────────────────────────────────────────────────────

import StandardEditor from './StandardEditor.jsx';
import { setup } from './_standardEditor.fixtures.js';

describe('threshold impact dialog', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('shows the dialog when the dry run reports changed dimensions, and saves on confirm', async () => {
    const { saveOverrides, previewOverrides } = setup({ previewResult: { changedDimensions: ['maintainability'] } });
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);

    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '60' } });
    const toolbarSaveBtn = await screen.findByRole('button', { name: /^save$/i });
    fireEvent.click(toolbarSaveBtn);

    await waitFor(() => expect(previewOverrides).toHaveBeenCalledOnce());
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/maintainability/i)).toBeInTheDocument();
    expect(saveOverrides).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      expect(saveOverrides).toHaveBeenCalledOnce();
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('saves directly when the dry run reports no changed dimensions', async () => {
    const { saveOverrides, previewOverrides } = setup({ previewResult: { changedDimensions: [] } });
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);

    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '60' } });
    const saveBtn = await screen.findByRole('button', { name: /^save$/i });
    fireEvent.click(saveBtn);

    await waitFor(() => expect(previewOverrides).toHaveBeenCalledOnce());
    await waitFor(() => expect(saveOverrides).toHaveBeenCalledOnce());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('cancel keeps the draft and does not save', async () => {
    const { saveOverrides } = setup({ previewResult: { changedDimensions: ['maintainability'] } });
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);

    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '60' } });
    const toolbarSaveBtn = await screen.findByRole('button', { name: /^save$/i });
    fireEvent.click(toolbarSaveBtn);

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /^cancel$/i }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(saveOverrides).not.toHaveBeenCalled();
    // draft still dirty: toolbar Save button remains and is enabled
    const savedBtn = screen.getByRole('button', { name: /^save$/i });
    expect(savedBtn).toBeInTheDocument();
    expect(savedBtn).not.toBeDisabled();
  });

  it('save-and-rescan saves then calls onRescan with the changed dimensions', async () => {
    const { saveOverrides } = setup({ previewResult: { changedDimensions: ['maintainability'] } });
    const onRescan = vi.fn();
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} onRescan={onRescan} />);

    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '60' } });
    const toolbarSaveBtn = await screen.findByRole('button', { name: /^save$/i });
    fireEvent.click(toolbarSaveBtn);

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /save and re-scan now/i }));

    await waitFor(() => {
      expect(saveOverrides).toHaveBeenCalledOnce();
      expect(onRescan).toHaveBeenCalledWith(['maintainability']);
    });
  });
});
