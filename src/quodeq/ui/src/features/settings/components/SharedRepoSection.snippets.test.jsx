import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import { makeFakeApi, renderWithApi } from './_sharedRepoSection.fixtures.jsx';

const URL = 'https://github.com/team/results.git';

describe('SharedRepoSection snippets choice', () => {
  it('shows code sharing off by default and saves the opt-in', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: URL, withSnippets: false })),
      setSharedSnippets: vi.fn(async (withSnippets) => ({ withSnippets })),
    });
    renderWithApi(fakeApi);

    await waitFor(() => expect(screen.getByText('Share code snippets')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Off' })).toHaveAttribute('aria-pressed', 'true');

    await userEvent.click(screen.getByRole('button', { name: 'On' }));
    expect(fakeApi.setSharedSnippets).toHaveBeenCalledWith(true);
  });

  it('has no snippets choice until a repository is connected', async () => {
    renderWithApi(makeFakeApi());
    await waitFor(() => expect(screen.getByText(/not configured/i)).toBeInTheDocument());
    expect(screen.queryByText('Share code snippets')).toBeNull();
  });
});
