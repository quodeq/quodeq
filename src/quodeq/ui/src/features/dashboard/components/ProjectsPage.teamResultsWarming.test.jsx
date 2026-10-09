import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ProjectsPage from './ProjectsPage.jsx';
import { LOCAL, SHARED, makeApi, pageActions, renderPage } from './_projectsPageTeam.fixtures.jsx';

afterEach(() => { vi.clearAllMocks(); });

// The server lists a shared card only once the project is fully warmed and
// counts the rest in `warmup`. One dashed placeholder per card still being
// warmed heads the list, so the team's results arrive one by one.
const listing = (projects, warmup) => vi.fn(async () => ({ projects, warmup, lastSynced: null, stale: false }));
const placeholders = () => document.querySelectorAll('.projects-row--placeholder');

describe('ProjectsPage — shared cards still being warmed', () => {
  it('shows one placeholder per card the server has not shown yet, next to the cards it has', async () => {
    const { api } = makeApi({
      configured: true,
      sharedListProjects: listing([SHARED], { active: true, projectsDone: 1, projectsTotal: 3, currentProjectName: 'two' }),
    });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    expect(placeholders()).toHaveLength(2);
    // The strip says so too, so nobody wonders whether the rest are coming.
    expect(screen.getByText('loading results · 1 of 3 ready…')).toBeInTheDocument();
  });

  it('on an empty page the placeholders stand in until the first card lands', async () => {
    const { api } = makeApi({
      configured: true,
      sharedListProjects: listing([], { active: true, projectsDone: 0, projectsTotal: 2, currentProjectName: 'one' }),
    });
    renderPage(api, <ProjectsPage projects={[]} actions={pageActions} />);
    await waitFor(() => expect(placeholders()).toHaveLength(2));
    expect(screen.getByText('Published evaluations will appear here when reading finishes.')).toBeInTheDocument();
    expect(screen.queryByText(/No repositories yet\./)).not.toBeInTheDocument();
  });

  it('shows no placeholder once the warm-up is done', async () => {
    const { api } = makeApi({
      configured: true,
      sharedListProjects: listing([SHARED], { active: false, projectsDone: 3, projectsTotal: 3, currentProjectName: null }),
    });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    expect(placeholders()).toHaveLength(0);
  });
});
