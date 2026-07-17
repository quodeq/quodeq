import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import '@testing-library/jest-dom/vitest';
import LastFetchedLine, { relativeTime } from './LastFetchedLine.jsx';

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

// Minor 7 (final whole-branch review): `new Date(null)` coerces to epoch 0
// rather than Invalid Date, so a bare NaN guard let relativeTime(null) render
// "57 years ago" instead of being treated as absent.
describe('relativeTime null/undefined guard', () => {
  it('returns null for null', () => {
    expect(relativeTime(null)).toBeNull();
  });

  it('returns null for undefined', () => {
    expect(relativeTime(undefined)).toBeNull();
  });

  it('still returns null for a genuinely invalid date string', () => {
    expect(relativeTime('not-a-date')).toBeNull();
  });

  it('still computes a real relative time for a valid timestamp', () => {
    const t = new Date(Date.now() - 3 * 86400 * 1000).toISOString();
    expect(relativeTime(t)).toBe('3 days ago');
  });
});
