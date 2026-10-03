import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import EvaluationsRepoForm from './EvaluationsRepoForm.jsx';

const NOT_A_REPO = 'That folder is not a git repository. Run git init there first, or point at a bare repository.';

describe('EvaluationsRepoForm', () => {
  it('submits a pasted url, trimmed', async () => {
    const user = userEvent.setup();
    const onConnect = vi.fn();
    render(<EvaluationsRepoForm onConnect={onConnect} browseFolder={async () => null} />);
    await user.type(screen.getByRole('textbox', { name: /evaluations repository url/i }), '  https://github.com/team/evals.git ');
    await user.click(screen.getByRole('button', { name: 'connect' }));
    expect(onConnect).toHaveBeenCalledWith('https://github.com/team/evals.git');
  });

  it('submits a chosen folder as a file url', async () => {
    const user = userEvent.setup();
    const onConnect = vi.fn();
    render(<EvaluationsRepoForm onConnect={onConnect} browseFolder={async () => '/Users/me/evals.git'} />);
    await user.click(screen.getByRole('radio', { name: 'choose a local folder' }));
    await user.click(screen.getByRole('button', { name: 'choose a folder' }));
    await user.click(screen.getByRole('button', { name: 'connect' }));
    expect(onConnect).toHaveBeenCalledWith('file:///Users/me/evals.git');
  });

  it('a cancelled folder pick keeps connect disabled', async () => {
    const user = userEvent.setup();
    const onConnect = vi.fn();
    render(<EvaluationsRepoForm onConnect={onConnect} browseFolder={async () => null} />);
    await user.click(screen.getByRole('radio', { name: 'choose a local folder' }));
    await user.click(screen.getByRole('button', { name: 'choose a folder' }));
    expect(screen.getByText('no folder chosen yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'connect' })).toBeDisabled();
  });

  it('the folder source hints at a bare repository', async () => {
    const user = userEvent.setup();
    render(<EvaluationsRepoForm onConnect={() => {}} browseFolder={async () => null} />);
    expect(screen.queryByText(/prefer a bare repository/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'choose a local folder' }));
    expect(screen.getByText('prefer a bare repository (git init --bare). publishing into a checked-out branch is refused.')).toBeInTheDocument();
  });

  it('shows the not-a-git-repository copy under the field and keeps the folder', async () => {
    render(<EvaluationsRepoForm onConnect={() => {}} error={NOT_A_REPO} initialUrl="file:///Users/me/plain" />);
    expect(screen.getByRole('alert')).toHaveTextContent(/not a git repository/);
    expect(screen.getByText('/Users/me/plain')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'choose a local folder' })).toBeChecked();
  });

  it('while connecting the button says so and does not submit again', async () => {
    const user = userEvent.setup();
    const onConnect = vi.fn();
    render(<EvaluationsRepoForm onConnect={onConnect} connecting initialUrl="https://github.com/team/evals.git" />);
    const button = screen.getByRole('button', { name: 'connecting…' });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(onConnect).not.toHaveBeenCalled();
  });
});
