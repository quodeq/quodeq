import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { SidePaneProvider } from './SidePaneProvider.jsx';
import { useSidePane } from './SidePaneContext.jsx';

function ToastProbe() {
  const { showToast } = useSidePane();
  return <button onClick={() => showToast('blocked: try again later')}>fire</button>;
}

describe('SidePaneProvider toast dismiss accessibility', () => {
  it('dismiss is a real button reachable via getByRole, and pressing it removes the toast', () => {
    render(<SidePaneProvider><ToastProbe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByText('blocked: try again later')).toBeInTheDocument();

    const dismiss = screen.getByRole('button', { name: 'Dismiss notification' });
    fireEvent.click(dismiss);
    expect(screen.queryByText('blocked: try again later')).toBeNull();
  });

  it('keeps the toast container itself a status live region', () => {
    render(<SidePaneProvider><ToastProbe /></SidePaneProvider>);
    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByRole('status')).toHaveTextContent('blocked: try again later');
  });
});
