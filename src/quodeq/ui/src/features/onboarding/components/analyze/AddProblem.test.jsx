import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import AddProblem from './AddProblem.jsx';

vi.mock('../../../github-access/components/AccessPanel.jsx', () => ({
  default: ({ failure, url }) => <div data-testid="access-panel">{failure.kind} · {url}</div>,
}));

const URL = 'https://github.com/acme/billing.git';
const idle = { run: vi.fn(), accessFailure: null, startError: null };

describe('AddProblem', () => {
  it('renders nothing while nothing stopped the add', () => {
    const { container } = render(<AddProblem add={idle} url={URL} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('an access failure opens the access panel for the url', () => {
    render(<AddProblem add={{ ...idle, accessFailure: { kind: 'auth_required', host: 'github.com', isGitHub: true } }} url={URL} />);
    expect(screen.getByTestId('access-panel')).toHaveTextContent(`auth_required · ${URL}`);
  });

  it('a start error shows the message, its detail and retry', () => {
    const retry = vi.fn();
    render(<AddProblem add={{ ...idle, startError: { message: 'could not clone the repository', detail: 'fatal: not found', retry } }} url={URL} />);
    expect(screen.getByRole('alert')).toHaveTextContent('could not clone the repository');
    expect(screen.getByText('fatal: not found')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
