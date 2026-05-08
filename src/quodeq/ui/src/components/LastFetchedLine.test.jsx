import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import '@testing-library/jest-dom/vitest';
import LastFetchedLine from './LastFetchedLine.jsx';

describe('LastFetchedLine', () => {
  it('renders nothing when lastFetchedAt is null', () => {
    const { container } = render(<LastFetchedLine lastFetchedAt={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when lastFetchedAt is undefined', () => {
    const { container } = render(<LastFetchedLine lastFetchedAt={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders "today" for a timestamp under 24 hours old', () => {
    const t = new Date(Date.now() - 30 * 60 * 1000).toISOString();
    render(<LastFetchedLine lastFetchedAt={t} />);
    expect(screen.getByText(/last updated today/i)).toBeInTheDocument();
  });

  it('renders "yesterday" for a timestamp 1 day old', () => {
    const t = new Date(Date.now() - 30 * 3600 * 1000).toISOString();
    render(<LastFetchedLine lastFetchedAt={t} />);
    expect(screen.getByText(/last updated yesterday/i)).toBeInTheDocument();
  });

  it('renders "N days ago" for a timestamp under 60 days old', () => {
    const t = new Date(Date.now() - 3 * 86400 * 1000).toISOString();
    render(<LastFetchedLine lastFetchedAt={t} />);
    expect(screen.getByText(/last updated 3 days ago/i)).toBeInTheDocument();
  });

  it('renders "N months ago" for a timestamp over 60 days old', () => {
    const t = new Date(Date.now() - 90 * 86400 * 1000).toISOString();
    render(<LastFetchedLine lastFetchedAt={t} />);
    expect(screen.getByText(/last updated 3 months ago/i)).toBeInTheDocument();
  });

  it('renders nothing when given an invalid date string', () => {
    const { container } = render(<LastFetchedLine lastFetchedAt="not-a-date" />);
    expect(container).toBeEmptyDOMElement();
  });
});
