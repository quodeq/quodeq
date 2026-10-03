import { it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import SignInCard from './SignInCard.jsx';

const code = { userCode: 'ABCD-1234', verificationUri: 'https://github.com/login/device', expiresIn: 900, interval: 5 };

it('shows the code while waiting, then the login, and reports it', async () => {
  const statuses = [{ state: 'awaiting_user' }, { state: 'done', login: 'victor' }];
  const api = { startDeviceFlow: vi.fn(async () => code), getDeviceFlow: vi.fn(async () => statuses.shift()) };
  const onSignedIn = vi.fn();
  const openExternal = vi.fn();
  render(<ApiProvider value={api}><SignInCard onSignedIn={onSignedIn} pollMs={5} openExternal={openExternal} /></ApiProvider>);
  fireEvent.click(screen.getByRole('button', { name: /sign in with github/i }));
  await waitFor(() => expect(screen.getByText('ABCD-1234')).toBeInTheDocument());
  expect(screen.getByText(/waiting for you to approve/i)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText(/signed in as victor/i)).toBeInTheDocument());
  expect(onSignedIn).toHaveBeenCalledWith('victor');
  expect(openExternal).toHaveBeenCalledTimes(1);
  expect(openExternal).toHaveBeenCalledWith(code.verificationUri);
});

it('expired offers start again', async () => {
  const api = { startDeviceFlow: vi.fn(async () => code), getDeviceFlow: vi.fn(async () => ({ state: 'expired' })) };
  render(<ApiProvider value={api}><SignInCard onSignedIn={vi.fn()} pollMs={5} openExternal={vi.fn()} /></ApiProvider>);
  fireEvent.click(screen.getByRole('button', { name: /sign in with github/i }));
  await waitFor(() => expect(screen.getByText(/that code expired/i)).toBeInTheDocument());
  expect(screen.getByRole('button', { name: /start again/i })).toBeInTheDocument();
});
