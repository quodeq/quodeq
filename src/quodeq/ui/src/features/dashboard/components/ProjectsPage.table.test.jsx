import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import ProjectsPage from './ProjectsPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// The Repositories table itself: the column headers sort, the files column
// shows each project's size, a row opens its project, and the ⋯ menu holds
// the rare actions. Without a server there is no location or sync column.
function makeFakeApi() {
  const api = {
    getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
  };
  return { getSyncStatus: (...a) => api.getSharedStatus(...a), ...api };
}

// Returns `rerender(props)` that keeps the same providers and query client.
function renderPage(props) {
  const QC = withQueryClient();
  const api = makeFakeApi();
  const tree = (p) => (
    <QC>
      <ApiProvider value={api}>
        <SidePaneProvider><ProjectsPage {...p} /></SidePaneProvider>
      </ApiProvider>
    </QC>
  );
  const view = render(tree(props));
  return { ...view, rerender: (p) => view.rerender(tree(p)) };
}

const PROJECTS = [
  { id: 'big', name: 'big', filesCount: 3925, latestDate: '2026-10-08' },
  { id: 'ui', name: 'ui', parent: 'big', filesCount: 61, latestDate: '2026-05-10' },
  { id: 'small', name: 'small', filesCount: 706, latestDate: '2026-10-03' },
];

const rowOf = (name) => screen.getByRole('button', { name }).closest('[role="row"]');

describe('ProjectsPage — the table', () => {
  it('shows each project\'s file count, and a subproject right under its parent', async () => {
    renderPage({ projects: PROJECTS, actions: {} });
    await waitFor(() => expect(screen.getByText('3,925')).toBeInTheDocument());
    expect(within(rowOf('small')).getByText('706')).toBeInTheDocument();
    expect(rowOf('ui')).toHaveClass('projects-row--child');
    const order = screen.getAllByRole('row').map((r) => r.querySelector('.projects-row__open')?.textContent).filter(Boolean);
    expect(order).toEqual(['big', 'ui', 'small']);
  });

  it('clicking a header sorts by it, and clicking the active one reverses it', async () => {
    const user = userEvent.setup();
    const onFiltersChange = vi.fn();
    const { rerender } = renderPage({ projects: PROJECTS, filters: {}, actions: { onFiltersChange } });
    await user.click(await screen.findByRole('button', { name: /^files/ }));
    expect(onFiltersChange).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'files', dir: 'desc' }));
    expect(screen.getByRole('columnheader', { name: /last run/ })).toHaveAttribute('aria-sort', 'descending');
    rerender({ projects: PROJECTS, filters: { sort: 'files', dir: 'desc' }, actions: { onFiltersChange } });
    await user.click(screen.getByRole('button', { name: /^files/ }));
    expect(onFiltersChange).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'files', dir: 'asc' }));
  });

  it('clicking a row or its name opens the project', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderPage({ projects: PROJECTS, actions: { onSelect } });
    await user.click(await screen.findByText('706'));
    expect(onSelect).toHaveBeenLastCalledWith('small', undefined);
    screen.getByRole('button', { name: 'big' }).focus();
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenLastCalledWith('big', undefined);
  });

  it('the ⋯ menu exports, and delete asks first, under the row', async () => {
    const user = userEvent.setup();
    const onExport = vi.fn();
    const onDelete = vi.fn();
    const onSelect = vi.fn();
    renderPage({ projects: PROJECTS, actions: { onExport, onDelete, onSelect } });
    await user.click(await screen.findByRole('button', { name: 'more actions for small' }));
    await user.click(screen.getByRole('menuitem', { name: 'export .zip' }));
    expect(onExport).toHaveBeenCalledWith('small');
    await user.click(screen.getByRole('button', { name: 'more actions for small' }));
    await user.click(screen.getByRole('menuitem', { name: 'delete' }));
    expect(onDelete).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Yes' }));
    expect(onDelete).toHaveBeenCalledWith('small');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('without a server, a missing folder says so under the name and offers relocate', async () => {
    const user = userEvent.setup();
    renderPage({ projects: [{ id: 'gone', name: 'gone', location: 'local', pathExists: false, path: '/old/gone' }], actions: { onRelocate: vi.fn() } });
    await waitFor(() => expect(screen.getAllByText('Path not found').length).toBeGreaterThan(0));
    expect(screen.queryByRole('columnheader', { name: 'location' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'relocate' }));
    expect(screen.getByLabelText('New project path')).toHaveValue('/old/gone');
  });
});
