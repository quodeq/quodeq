import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const refreshProject = vi.fn();
vi.mock('../../../../api/projects.js', () => ({ refreshProject: (...args) => refreshProject(...args) }));

import { CardFooter } from './CardFooter.jsx';

const TITLE = 'Fetch latest code';

function renderFooter(props = {}) {
  return render(<CardFooter name="proj-a" confirming={null} setConfirming={() => {}} {...props} />);
}

function refusal(code, detail) {
  return Object.assign(new Error('server sentence'), { status: 409, code, body: { detail } });
}

describe('CardFooter fetch latest code', () => {
  beforeEach(() => { refreshProject.mockReset(); });

  it('has no refresh button for a project without a remote', () => {
    renderFooter();
    expect(screen.queryByTitle(TITLE)).toBeNull();
  });

  it('reports how many commits an update brought in', async () => {
    refreshProject.mockResolvedValue({ outcome: 'updated', newCommits: 12, lastFetchedAt: null });
    renderFooter({ refreshable: true });

    fireEvent.click(screen.getByTitle(TITLE));

    expect(await screen.findByRole('status')).toHaveTextContent('Updated, 12 new commits.');
    expect(refreshProject).toHaveBeenCalledWith('proj-a');
  });

  it('uses the singular for one commit', async () => {
    refreshProject.mockResolvedValue({ outcome: 'updated', newCommits: 1, lastFetchedAt: null });
    renderFooter({ refreshable: true });

    fireEvent.click(screen.getByTitle(TITLE));

    expect(await screen.findByRole('status')).toHaveTextContent('Updated, 1 new commit.');
  });

  it('says so when there was nothing new', async () => {
    refreshProject.mockResolvedValue({ outcome: 'up_to_date', newCommits: 0, lastFetchedAt: null });
    renderFooter({ refreshable: true });

    fireEvent.click(screen.getByTitle(TITLE));

    expect(await screen.findByRole('status')).toHaveTextContent('Already up to date.');
  });

  it('shows the translated refusal with git output as its tooltip', async () => {
    refreshProject.mockRejectedValue(refusal('DIRTY', 'M a.txt'));
    renderFooter({ refreshable: true });

    fireEvent.click(screen.getByTitle(TITLE));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('This folder has uncommitted changes. Update it with git yourself.');
    expect(alert).toHaveAttribute('title', 'M a.txt');
  });

  it('falls back to the server sentence for an unmapped code', async () => {
    refreshProject.mockRejectedValue(refusal('NOT_FOUND'));
    renderFooter({ refreshable: true });

    fireEvent.click(screen.getByTitle(TITLE));

    expect(await screen.findByRole('alert')).toHaveTextContent('server sentence');
  });

  it('ignores a second click while the first is still running', async () => {
    let finish;
    refreshProject.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    renderFooter({ refreshable: true });

    fireEvent.click(screen.getByTitle(TITLE));
    const pending = await screen.findByTitle('Fetching latest code...');
    expect(pending).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(pending);
    expect(refreshProject).toHaveBeenCalledTimes(1);

    finish({ outcome: 'up_to_date', newCommits: 0, lastFetchedAt: null });
    expect(await screen.findByTitle(TITLE)).not.toHaveAttribute('aria-disabled');
  });

  it('does not select the card when clicked', () => {
    refreshProject.mockReturnValue(new Promise(() => {}));
    const onCardClick = vi.fn();
    render(
      <div onClick={onCardClick}>
        <CardFooter name="proj-a" confirming={null} setConfirming={() => {}} refreshable />
      </div>,
    );

    fireEvent.click(screen.getByTitle(TITLE));

    expect(onCardClick).not.toHaveBeenCalled();
  });
});
