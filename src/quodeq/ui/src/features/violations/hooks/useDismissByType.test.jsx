import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useDismissByType } from './useDismissByType.js';
import { DISMISS_SCOPE } from '../violationsVocab.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

const confirm = vi.fn(async () => true);
vi.mock('../../../utils/confirmDialog.js', () => ({ confirmDialog: (...a) => confirm(...a) }));

const row = { req: 'M-MDF-1', dimension: 'maintainability', principle: 'Modifiability', runId: 'r1', now: 3, violations: [{}, {}, {}] };

function Probe({ selectedSource, scope, onReconcile }) {
  const { dismissType, error, notice } = useDismissByType({ project: 'p', selectedSource, onReconcile });
  return <><button type="button" onClick={() => dismissType(row, scope)}>go</button><span>{error}</span><em>{notice}</em></>;
}

function mount(api, props) {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}><ApiProvider value={api}><Probe {...props} /></ApiProvider></QueryClientProvider>);
}

describe('useDismissByType', () => {
  it('confirms, posts the scope and reconciles', async () => {
    const dismissByType = vi.fn(async () => ({ ok: true, dismissed: 3, scores: null, delta: { kind: 'dismiss_many', runId: 'r1', isLatest: true } }));
    const onReconcile = vi.fn();
    mount({ dismissByType }, { selectedSource: PROJECT_SOURCE.LOCAL, scope: DISMISS_SCOPE.PRINCIPLE, onReconcile });
    fireEvent.click(screen.getByText('go'));
    await waitFor(() => expect(dismissByType).toHaveBeenCalledWith('p', { req: 'M-MDF-1', dimension: 'maintainability', runId: 'r1', principle: 'Modifiability' }));
    expect(confirm).toHaveBeenCalled();
    expect(onReconcile).toHaveBeenCalled();
  });

  it('project scope sends no principle', async () => {
    const dismissByType = vi.fn(async () => ({ ok: true, dismissed: 3, scores: null, delta: { kind: 'dismiss_many' } }));
    mount({ dismissByType }, { selectedSource: PROJECT_SOURCE.LOCAL, scope: DISMISS_SCOPE.PROJECT });
    fireEvent.click(screen.getByText('go'));
    await waitFor(() => expect(dismissByType).toHaveBeenCalled());
    expect(dismissByType.mock.calls[0][1].principle).toBeUndefined();
  });

  it('does nothing on a shared project', async () => {
    const dismissByType = vi.fn();
    mount({ dismissByType }, { selectedSource: PROJECT_SOURCE.SHARED, scope: DISMISS_SCOPE.PROJECT });
    fireEvent.click(screen.getByText('go'));
    await new Promise((r) => setTimeout(r, 0));
    expect(dismissByType).not.toHaveBeenCalled();
  });

  it('reports a failure', async () => {
    const dismissByType = vi.fn(async () => { throw new Error('boom'); });
    mount({ dismissByType }, { selectedSource: PROJECT_SOURCE.LOCAL, scope: DISMISS_SCOPE.PROJECT });
    fireEvent.click(screen.getByText('go'));
    expect(await screen.findByText('Failed to dismiss the type. Please try again.')).toBeTruthy();
  });

  it('says so when the server dismissed a different count than the dialog promised', async () => {
    const dismissByType = vi.fn(async () => ({ ok: true, dismissed: 1, scores: null, delta: { kind: 'dismiss_many' } }));
    mount({ dismissByType }, { selectedSource: PROJECT_SOURCE.LOCAL, scope: DISMISS_SCOPE.PROJECT });
    fireEvent.click(screen.getByText('go'));
    expect(await screen.findByText('Dismissed 1 of the 3 findings shown; the rest were already dismissed or are not in this run.')).toBeTruthy();
  });
});
