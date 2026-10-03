import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import StandardsModal from './StandardsModal.jsx';

describe('StandardsModal', () => {
  it('renders a plain dialog box with the title, body, Cancel and the given actions', () => {
    const { container } = render(
      <StandardsModal title="Delete" onCancel={() => {}} actions={<button type="button">Go</button>}><p>body</p></StandardsModal>,
    );
    const dialog = container.querySelector('.modal-overlay > .modal-dialog');
    expect([dialog.hasAttribute('role'), dialog.querySelector('h3.modal-title').outerHTML, dialog.querySelector('p').textContent,
      [...dialog.querySelectorAll('.modal-actions button')].map((b) => b.textContent)])
      .toEqual([false, '<h3 class="modal-title">Delete</h3>', 'body', ['Cancel', 'Go']]);
  });

  it('becomes a labelled modal dialog when given a title id', () => {
    render(<StandardsModal title="Thresholds" titleId="tid" onCancel={() => {}} />);
    const dialog = screen.getByRole('dialog', { name: 'Thresholds' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
  });

  it('cancels on an overlay click or Cancel, but not on a click inside the dialog', () => {
    const onCancel = vi.fn();
    const { container } = render(<StandardsModal title="T" onCancel={onCancel}><p>inside</p></StandardsModal>);
    fireEvent.click(screen.getByText('inside'));
    fireEvent.click(container.querySelector('.modal-overlay'));
    fireEvent.click(screen.getByText('Cancel'));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });
});
