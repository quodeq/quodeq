import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { VerificationBadge } from './VerificationBadge.jsx';

describe('VerificationBadge', () => {
  it('renders null when verification is null', () => {
    const { container } = render(<VerificationBadge verification={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders null when verification is undefined', () => {
    const { container } = render(<VerificationBadge verification={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders false_positive verdict with label', () => {
    const { unmount } = render(
      <VerificationBadge verification={{ verdict: 'false_positive', confidence: 0.8 }} />
    );
    expect(screen.getByText(/false positive/i)).toBeInTheDocument();
    unmount();
  });

  it('renders confirmed verdict with label', () => {
    const { unmount } = render(
      <VerificationBadge verification={{ verdict: 'confirmed', confidence: 0.8 }} />
    );
    expect(screen.getByText(/confirmed/i)).toBeInTheDocument();
    unmount();
  });

  it('renders inconclusive verdict with label', () => {
    const { unmount } = render(
      <VerificationBadge verification={{ verdict: 'inconclusive', confidence: 0.8 }} />
    );
    expect(screen.getByText(/inconclusive/i)).toBeInTheDocument();
    unmount();
  });

  it('renders not_applicable verdict with label', () => {
    const { unmount } = render(
      <VerificationBadge verification={{ verdict: 'not_applicable', confidence: 1.0 }} />
    );
    expect(screen.getByText(/not applicable/i)).toBeInTheDocument();
    unmount();
  });

  it('shows confidence percentage for confident verdicts', () => {
    render(
      <VerificationBadge verification={{ verdict: 'false_positive', confidence: 0.82 }} />
    );
    expect(screen.getByText(/82%/)).toBeInTheDocument();
  });

  it('omits confidence percentage for not_applicable verdict', () => {
    const { container } = render(
      <VerificationBadge verification={{ verdict: 'not_applicable', confidence: 1.0 }} />
    );
    expect(container.textContent).not.toMatch(/%/);
  });
});
