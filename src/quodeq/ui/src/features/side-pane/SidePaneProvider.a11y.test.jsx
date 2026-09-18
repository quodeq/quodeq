import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider, SidePaneToast } from './SidePaneProvider.jsx';
import { useSidePane } from './SidePaneContext.jsx';

function ToastProbe() {
  const { showToast } = useSidePane();
  return <button onClick={() => showToast('blocked: try again later')}>fire</button>;
}

describe('SidePaneProvider toast dismiss accessibility', () => {
  it('dismiss is a real button reachable via getByRole, and pressing it removes the toast', () => {
    render(<SidePaneProvider><ToastProbe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('fire'));
    expect(document.querySelector('.side-pane-toast')).toHaveTextContent('blocked: try again later');

    const dismiss = screen.getByRole('button', { name: 'Dismiss notification' });
    fireEvent.click(dismiss);
    expect(document.querySelector('.side-pane-toast')).toBeNull();
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });

  it('keeps the toast container itself a status live region', () => {
    render(<SidePaneProvider><ToastProbe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByRole('status')).toHaveTextContent('blocked: try again later');
  });

  it('keeps one live region mounted and empty until a notice arrives', () => {
    render(<SidePaneProvider><ToastProbe /></SidePaneProvider>);
    const status = screen.getByRole('status');
    expect(status).toBeEmptyDOMElement();
    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByRole('status')).toHaveTextContent('blocked: try again later');
  });

  it('dismisses when the container is clicked, the mouse convenience the cursor promises', () => {
    const onDismiss = vi.fn();
    render(<SidePaneToast notice={{ message: 'at cap' }} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByText('at cap'));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('dismisses once when the dismiss button is clicked, not twice through the container', () => {
    const onDismiss = vi.fn();
    render(<SidePaneToast notice={{ message: 'at cap' }} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
