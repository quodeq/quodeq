import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import IncompleteSetupCard from './IncompleteSetupCard.jsx';

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
