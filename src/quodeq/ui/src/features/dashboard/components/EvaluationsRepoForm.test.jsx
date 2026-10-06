import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import EvaluationsRepoForm from './EvaluationsRepoForm.jsx';

const NOT_A_REPO = 'That folder is not a git repository. Run git init there first, or point at a bare repository.';
const BARE_HINT = 'prefer a bare repository (git init --bare). publishing into a checked-out branch is refused.';

describe('EvaluationsRepoForm', () => {
  it('submits a pasted url, trimmed', async () => {
    const user = userEvent.setup();
    const onConnect = vi.fn();
    render(<EvaluationsRepoForm onConnect={onConnect} browseFolder={async () => null} />);
    await user.type(screen.getByRole('textbox', { name: /evaluations repository url/i }), '  https://github.com/team/evals.git ');
    await user.click(screen.getByRole('button', { name: 'connect' }));
    expect(onConnect).toHaveBeenCalledWith('https://github.com/team/evals.git');
    expect(screen.queryByText(BARE_HINT)).not.toBeInTheDocument();
  });

  it('local folder fills the field with the picked folder as a file url and submits it', async () => {
    const user = userEvent.setup();
    const onConnect = vi.fn();
    render(<EvaluationsRepoForm onConnect={onConnect} browseFolder={async () => '/Users/me/evals.git'} />);
    await user.click(screen.getByRole('button', { name: 'local folder' }));
    expect(screen.getByRole('textbox', { name: /evaluations repository url/i })).toHaveValue('file:///Users/me/evals.git');
    expect(screen.getByText(BARE_HINT)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'connect' }));
    expect(onConnect).toHaveBeenCalledWith('file:///Users/me/evals.git');
  });

  it('a host without a scheme is a remote, sent as https', async () => {
    const user = userEvent.setup();
    const onConnect = vi.fn();
    render(<EvaluationsRepoForm onConnect={onConnect} browseFolder={async () => null} />);
    await user.type(screen.getByRole('textbox', { name: /evaluations repository url/i }), 'github.com/team/evals');
    expect(screen.queryByText(BARE_HINT)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'connect' }));
    expect(onConnect).toHaveBeenCalledWith('https://github.com/team/evals');
  });

  it('a typed path is a local folder too, sent as a file url', async () => {
    const user = userEvent.setup();
    const onConnect = vi.fn();
    render(<EvaluationsRepoForm onConnect={onConnect} browseFolder={async () => null} />);
    await user.type(screen.getByRole('textbox', { name: /evaluations repository url/i }), '/Users/me/evals.git');
    expect(screen.getByText(BARE_HINT)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'connect' }));
    expect(onConnect).toHaveBeenCalledWith('file:///Users/me/evals.git');
  });

  it('a cancelled folder pick leaves the field empty and connect disabled', async () => {
    const user = userEvent.setup();
    const onConnect = vi.fn();
    render(<EvaluationsRepoForm onConnect={onConnect} browseFolder={async () => null} />);
    await user.click(screen.getByRole('button', { name: 'local folder' }));
    expect(screen.getByRole('textbox', { name: /evaluations repository url/i })).toHaveValue('');
    expect(screen.getByRole('button', { name: 'connect' })).toBeDisabled();
  });

  it('without a picker there is no local folder button', () => {
    render(<EvaluationsRepoForm onConnect={() => {}} />);
    expect(screen.queryByRole('button', { name: 'local folder' })).not.toBeInTheDocument();
  });

  it('shows the not-a-git-repository copy under the field and keeps the folder', () => {
    render(<EvaluationsRepoForm onConnect={() => {}} error={NOT_A_REPO} initialUrl="file:///Users/me/plain" />);
    expect(screen.getByRole('alert')).toHaveTextContent(/not a git repository/);
    expect(screen.getByRole('textbox', { name: /evaluations repository url/i })).toHaveValue('file:///Users/me/plain');
  });

  it('renders the caller\'s secondary action at the left of connect', () => {
    render(<EvaluationsRepoForm onConnect={() => {}} secondaryAction={<button type="button">cancel</button>} />);
    const buttons = screen.getAllByRole('button').map((b) => b.textContent);
    expect(buttons).toEqual(['cancel', 'connect']);
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
