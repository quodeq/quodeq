import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ScopePicker from './ScopePicker.jsx';

const rows = [{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }];

function renderPicker(scopeIds, scopeCount) {
  render(
    <ScopePicker
      pickerOpen
      setPickerOpen={vi.fn()}
      rows={rows}
      scopeIds={scopeIds}
      scopeCount={scopeCount}
      toggleProject={vi.fn()}
      selectAll={vi.fn()}
      selectFlagged={vi.fn()}
    />,
  );
}

describe('ScopePicker', () => {
  it('marks the rows inside the scope on', () => {
    renderPicker(['b'], 1);
    const [rowA, rowB] = screen.getAllByRole('checkbox');
    expect(rowA).not.toBeChecked();
    expect(rowB).toBeChecked();
  });

  it('treats a null scope as everything on', () => {
    renderPicker(null, rows.length);
    const [rowA, rowB] = screen.getAllByRole('checkbox');
    expect(rowA).toBeChecked();
    expect(rowB).toBeChecked();
  });
});
