import { render as rtlRender, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import IncompleteSetupCard from './IncompleteSetupCard.jsx';

// The card follows the shared clone slot (a url completes as a 202 job).
function render(ui) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const api = { registerProject: vi.fn(), getCloneStatus: vi.fn(async () => null) };
  return rtlRender(ui, { wrapper: ({ children }) => <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider> });
}

describe('IncompleteSetupCard', () => {
  it('renders nothing for local projects', () => {
    const { container } = render(<IncompleteSetupCard projectInfo={{ location: 'local' }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when projectInfo is null', () => {
    const { container } = render(<IncompleteSetupCard projectInfo={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the CTA for online projects', () => {
    render(<IncompleteSetupCard projectInfo={{ location: 'online', path: 'https://x/y.git' }} />);
    expect(screen.getByRole('button', { name: /complete setup/i })).toBeInTheDocument();
  });

  it('clicking the CTA opens CloneTargetStep with the repo URL', () => {
    render(<IncompleteSetupCard projectInfo={{ location: 'online', path: 'https://x/y.git' }} />);
    fireEvent.click(screen.getByRole('button', { name: /complete setup/i }));
    expect(screen.getByText(/where should we clone this repo/i)).toBeInTheDocument();
  });
});
