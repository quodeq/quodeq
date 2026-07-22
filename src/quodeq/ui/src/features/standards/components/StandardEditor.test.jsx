/**
 * Tests for StandardEditor override state wiring (Task 9).
 * Covers: managed-standard Save enabled when override drafted;
 * handleChangeParam(null) clears an entry; customized badge count.
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

import { useStandardDetail } from '../hooks/useStandardDetail.js';
import { useStandardsOverrides } from '../hooks/useStandardsOverrides.js';
import { useAppState } from '../../../hooks/useAppState.js';
import StandardEditor from './StandardEditor.jsx';

// ── fixtures ──────────────────────────────────────────────────────────────────

const MANAGED_STANDARD = {
  id: 'iso-25010',
  name: 'ISO 25010',
  description: 'Quality standard',
  type: 'builtin',
  managed: true,
  principles: [
    {
      name: 'Maintainability',
      description: '',
      requirements: [
        {
          id: 'M-ANA-2',
          text: 'Functions MUST NOT exceed {max_lines} lines',
          description: '',
          refs: [],
          params: { max_lines: { label: 'Max function lines', type: 'int', default: 50, min: 10, max: 500 } },
        },
      ],
    },
  ],
};

// selectedNode pointing at the parameterised requirement so ThresholdFields is rendered
const REQ_NODE = { type: 'requirement', principleIndex: 0, reqIndex: 0 };

function makeDetail(extra = {}) {
  return {
    standard: MANAGED_STANDARD,
    loading: false,
    error: null,
    dirty: false,
    editable: false, // managed standard — structure is read-only
    selectedNode: REQ_NODE,
    setSelectedNode: vi.fn(),
    updateField: vi.fn(),
    addPrinciple: vi.fn(),
    removePrinciple: vi.fn(),
    addRequirement: vi.fn(),
    removeRequirement: vi.fn(),
    save: vi.fn().mockResolvedValue(undefined),
    ...extra,
  };
}

function setup({ projectId = 'proj-1', savedOverrides = {}, previewResult = { changedDimensions: [] } } = {}) {
  const saveOverrides = vi.fn().mockResolvedValue(undefined);
  const previewOverrides = vi.fn().mockResolvedValue(previewResult);
  useAppState.mockReturnValue({ selectedProject: projectId });
  useStandardsOverrides.mockReturnValue({ overrides: savedOverrides, counts: {}, loading: false, error: null, save: saveOverrides, preview: previewOverrides });
  useStandardDetail.mockReturnValue(makeDetail());
  return { saveOverrides, previewOverrides };
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe('StandardEditor — override state wiring', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('Save button is absent for a managed standard when there are no overrides drafted', () => {
    setup();
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);
    // editable=false and overridesDirty=false → no Save button
    expect(screen.queryByRole('button', { name: /^save$/i })).not.toBeInTheDocument();
  });

  it('Save button appears and is enabled once an override is drafted via ThresholdFields', async () => {
    setup();
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);

    // ThresholdFields renders because selectedNode=requirement & onChangeParam provided
    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '60' } });

    // Save button must appear and be enabled
    await waitFor(() => {
      const saveBtn = screen.getByRole('button', { name: /^save$/i });
      expect(saveBtn).toBeInTheDocument();
      expect(saveBtn).not.toBeDisabled();
    });
  });

  it('Save for managed standard calls saveOverrides with the drafted overrides', async () => {
    const { saveOverrides } = setup();
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);

    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '60' } });

    const saveBtn = await screen.findByRole('button', { name: /^save$/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(saveOverrides).toHaveBeenCalledOnce();
      const arg = saveOverrides.mock.calls[0][0];
      expect(arg['M-ANA-2']).toEqual({ max_lines: 60 });
    });
  });

  it('after save completes, the Save button is gone (draft cleared, managed standard)', async () => {
    setup();
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);

    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '60' } });

    const saveBtn = await screen.findByRole('button', { name: /^save$/i });
    fireEvent.click(saveBtn);

    // For a managed standard, once draft is cleared (overridesDirty=false)
    // AND editable=false, the Save button is removed from the DOM.
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /^save$/i })).not.toBeInTheDocument();
    });
  });

  it('handleChangeParam(null) removes the param key; when reqOverrides is empty the req key is deleted', async () => {
    // Start with an active override so the Reset button is visible
    const { saveOverrides } = setup({ savedOverrides: { 'M-ANA-2': { max_lines: 60 } } });
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);

    const resetBtn = screen.getByRole('button', { name: /reset to default/i });
    fireEvent.click(resetBtn);

    // overridesDirty is true (draft = {}), Save still present and enabled
    const saveBtn = await screen.findByRole('button', { name: /^save$/i });
    expect(saveBtn).not.toBeDisabled();
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(saveOverrides).toHaveBeenCalledOnce();
      const arg = saveOverrides.mock.calls[0][0];
      // req key removed because no params remain overridden
      expect(arg['M-ANA-2']).toBeUndefined();
    });
  });

  it('customized badge shows count of requirements with active overrides in this standard', () => {
    setup({ savedOverrides: { 'M-ANA-2': { max_lines: 60 } } });
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);
    expect(screen.getByText(/1 thresholds customized/i)).toBeInTheDocument();
  });

  it('StandardTree labels show resolved override value, not raw placeholder', async () => {
    setup({ savedOverrides: { 'M-ANA-2': { max_lines: 75 } } });
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);
    // Expand the principle node so the requirement node renders
    const principleRow = screen.getByText('Maintainability');
    fireEvent.click(principleRow);
    // The tree node label should show the resolved text with "75", not the raw placeholder
    await waitFor(() => {
      expect(screen.getByText(/75 lines/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/\{max_lines\}/)).not.toBeInTheDocument();
  });

  it('customized badge is absent when no overrides exist', () => {
    setup({ savedOverrides: {} });
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);
    expect(screen.queryByText(/thresholds customized/i)).not.toBeInTheDocument();
  });

  it('when no project is selected, ThresholdFields is not rendered (onChangeParam=undefined)', () => {
    setup({ projectId: null });
    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);
    // ThresholdFields only renders when onChangeParam is provided
    expect(screen.queryByText(/^Thresholds$/i)).not.toBeInTheDocument();
  });

  it('failed saveOverrides shows an inline error and keeps the Save button (draft preserved)', async () => {
    const saveOverrides = vi.fn().mockRejectedValue(new Error('Network error'));
    const previewOverrides = vi.fn().mockResolvedValue({ changedDimensions: [] });
    useAppState.mockReturnValue({ selectedProject: 'proj-1' });
    useStandardsOverrides.mockReturnValue({ overrides: {}, counts: {}, loading: false, error: null, save: saveOverrides, preview: previewOverrides });
    useStandardDetail.mockReturnValue(makeDetail());

    render(<StandardEditor standardId="iso-25010" onBack={() => {}} />);

    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '60' } });

    const saveBtn = await screen.findByRole('button', { name: /^save$/i });
    fireEvent.click(saveBtn);

    // Error message appears inline
    await waitFor(() => {
      expect(screen.getByText(/Network error/i)).toBeInTheDocument();
    });
    // Save button is still present (draft not cleared)
    expect(screen.getByRole('button', { name: /^save$/i })).toBeInTheDocument();
  });

  it('onSaved is NOT called when saveOverrides rejects', async () => {
    const saveOverrides = vi.fn().mockRejectedValue(new Error('Server error'));
    const previewOverrides = vi.fn().mockResolvedValue({ changedDimensions: [] });
    const onSaved = vi.fn();
    useAppState.mockReturnValue({ selectedProject: 'proj-1' });
    useStandardsOverrides.mockReturnValue({ overrides: {}, counts: {}, loading: false, error: null, save: saveOverrides, preview: previewOverrides });
    useStandardDetail.mockReturnValue(makeDetail());

    render(<StandardEditor standardId="iso-25010" onBack={() => {}} onSaved={onSaved} />);

    const input = screen.getByLabelText('Max function lines');
    fireEvent.change(input, { target: { value: '60' } });

    const saveBtn = await screen.findByRole('button', { name: /^save$/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText(/Server error/i)).toBeInTheDocument();
    });
    expect(onSaved).not.toHaveBeenCalled();
  });
});

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
