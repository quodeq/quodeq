/**
 * Finding #249 – ServerSection must use getHealth() from api/index.js
 * (which goes through request() with a 30s timeout) instead of the
 * local ping() function that calls raw fetch with no timeout.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ServerLogContext } from '../server-log/ServerLogContext.js';

// Mock getHealth from api/index.js so we can assert it is called.
vi.mock('../../../api/index.js', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    getHealth: vi.fn(),
  };
});

import { getHealth } from '../../../api/index.js';
import ServerSection from './ServerSection.jsx';

const stubServerLog = { open: false, openLog: vi.fn(), closeLog: vi.fn() };

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ServerLogContext.Provider value={stubServerLog}>{children}</ServerLogContext.Provider>
      </QueryWrapper>
    );
  };
}

describe('#249 ServerSection uses getHealth() not raw fetch', () => {
  beforeEach(() => {
    getHealth.mockReset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls getHealth() when polling for server status', async () => {
    getHealth.mockResolvedValue({ ok: true, port: 7863, pid: 1, version: '1.0.0', address: '127.0.0.1' });
    const Wrapper = makeWrapper();
    render(<Wrapper><ServerSection /></Wrapper>);
    await waitFor(() => expect(getHealth).toHaveBeenCalled());
  });

  it('does not call raw fetch directly', async () => {
    getHealth.mockResolvedValue({ ok: true, port: 7863, pid: 1, version: '1.0.0', address: '127.0.0.1' });
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    const Wrapper = makeWrapper();
    render(<Wrapper><ServerSection /></Wrapper>);

    await waitFor(() => expect(getHealth).toHaveBeenCalled());
    // getHealth is mocked and doesn't call fetch, so fetch should never fire.
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('shows server details when getHealth resolves with ok data', async () => {
    getHealth.mockResolvedValue({ ok: true, port: 7863, pid: 1234, version: '1.0.6', address: '127.0.0.1' });
    const Wrapper = makeWrapper();
    render(<Wrapper><ServerSection /></Wrapper>);
    await waitFor(() => {
      expect(screen.getByText('7863')).toBeTruthy();
      expect(screen.getByText('1234')).toBeTruthy();
    });
  });

  it('shows offline when getHealth rejects', async () => {
    getHealth.mockRejectedValue(new Error('timeout'));
    const Wrapper = makeWrapper();
    render(<Wrapper><ServerSection /></Wrapper>);
    await waitFor(() => {
      expect(screen.getAllByText(/Restart/).length).toBeGreaterThan(0);
    });
  });
});
