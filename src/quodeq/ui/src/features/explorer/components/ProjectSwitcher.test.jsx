import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, within, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import NavBreadcrumb from './NavBreadcrumb.jsx';
import { buildSwitcherRows, filterSwitcherRows } from './projectSwitcherModel.js';
import { switchProject } from '../../../routes/switchProject.js';

const PROJECTS = [
  { id: 'p-old', name: 'old-repo', latestDate: '2026-01-01', latestGrade: 'C' },
  { id: 'p-new', name: 'new-repo', displayName: 'New Repo', latestDate: '2026-09-01', latestGrade: 'A' },
  { id: 'p-mid', name: 'api', parent: 'p-new', latestDate: '2026-05-01' },
];

function renderSwitcher(overrides = {}) {
  const switcher = {
    projects: PROJECTS,
    selectedProject: 'p-old',
    onPick: vi.fn(),
    onAllRepositories: vi.fn(),
    onAddProject: vi.fn(),
    ...overrides,
  };
  const onSelectProject = vi.fn();
  render(
    <NavBreadcrumb
      stack={[{ page: 'violations' }]}
      onGoTo={() => {}}
      projectName="old-repo"
      onSelectProject={onSelectProject}
      projectSwitcher={switcher}
    />,
  );
  return { switcher, onSelectProject };
}

const crumb = () => screen.getByRole('button', { name: /old-repo/ });
const search = () => screen.getByRole('combobox');
const optionLabels = () => screen.getAllByRole('option').map((o) => o.textContent);

afterEach(() => vi.restoreAllMocks());

describe('projectSwitcherModel', () => {
  it('sorts most recent first and labels subprojects parent / child', () => {
    expect(buildSwitcherRows(PROJECTS).map((r) => r.label)).toEqual(['New Repo', 'New Repo / api', 'old-repo']);
  });

  it('filters by display name and name, case-insensitive', () => {
    const rows = buildSwitcherRows(PROJECTS);
    expect(filterSwitcherRows(rows, 'NEW').map((r) => r.id)).toEqual(['p-new', 'p-mid']);
    expect(filterSwitcherRows(rows, 'new-repo').map((r) => r.id)).toEqual(['p-new']);
    expect(filterSwitcherRows(rows, '  ')).toBe(rows);
  });

  it('adds the remote projects with no local copy, tagged shared', () => {
    const shared = [
      { id: 'p-new', name: 'new-repo', latestDate: '2026-09-01' },
      { id: 's-team', name: 'team-repo', originUrl: 'https://github.com/acme/team', latestDate: '2026-07-01' },
      { id: 's-pulled', name: 'pulled', originUrl: 'https://github.com/acme/old', latestDate: '2026-02-01' },
    ];
    const locals = [...PROJECTS, { id: 'p-pulled', name: 'old-clone', originUrl: 'git@github.com:acme/old.git' }];
    const rows = buildSwitcherRows(locals, shared);
    expect(rows.map((r) => [r.id, r.source])).toEqual([
      ['p-new', 'local'], ['s-team', 'shared'], ['p-mid', 'local'], ['p-old', 'local'], ['p-pulled', 'local'],
    ]);
  });
});

describe('switchProject', () => {
  const nav = () => ({ handleProjectChange: vi.fn(), navTab: vi.fn() });

  it('from Repositories goes to the Overview', () => {
    const n = nav();
    switchProject(n, 'p', 'local');
    expect(n.handleProjectChange).toHaveBeenCalledWith('p', 'local');
    expect(n.navTab).toHaveBeenCalledWith('overview');
  });

  it('stays on a project-scoped tab root, and resets a drill-down to its tab', () => {
    const atRoot = nav();
    switchProject(atRoot, 'p', 'local', { rootTab: 'violations', depth: 1 });
    expect(atRoot.navTab).not.toHaveBeenCalled();
    const deep = nav();
    switchProject(deep, 'p', 'local', { rootTab: 'map', depth: 3 });
    expect(deep.navTab).toHaveBeenCalledWith('map');
  });
});

describe('NavBreadcrumb project switcher', () => {
  it('opens on crumb click instead of navigating, with the search focused', () => {
    const { onSelectProject } = renderSwitcher();
    expect(crumb()).toHaveAttribute('aria-haspopup', 'dialog');
    expect(crumb()).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(crumb());
    expect(onSelectProject).not.toHaveBeenCalled();
    expect(crumb()).toHaveAttribute('aria-expanded', 'true');
    expect(search()).toHaveFocus();
    expect(optionLabels()).toEqual(['New RepoA', 'New Repo / api', 'old-repoC']);
    // The current project is marked and starts highlighted.
    const current = screen.getByRole('option', { name: /old-repo/ });
    expect(current).toHaveAttribute('aria-current', 'true');
    expect(current).toHaveAttribute('aria-selected', 'true');
  });

  it('filters the list by the search query', () => {
    renderSwitcher();
    fireEvent.click(crumb());
    fireEvent.change(search(), { target: { value: 'api' } });
    expect(optionLabels()).toEqual(['New Repo / api']);
    fireEvent.change(search(), { target: { value: 'zzz' } });
    expect(screen.queryAllByRole('option')).toHaveLength(0);
    expect(screen.getByText('No matching projects')).toBeInTheDocument();
  });

  it('ArrowDown/ArrowUp move the highlight and Enter picks it', () => {
    const { switcher } = renderSwitcher();
    fireEvent.click(crumb());
    // Starts on the current project (last row); ArrowDown wraps to the top.
    fireEvent.keyDown(search(), { key: 'ArrowDown' });
    fireEvent.keyDown(search(), { key: 'ArrowDown' });
    fireEvent.keyDown(search(), { key: 'ArrowUp' });
    fireEvent.keyDown(search(), { key: 'Enter' });
    expect(switcher.onPick).toHaveBeenCalledWith('p-new', 'local');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Enter on a filtered list picks the first match', () => {
    const { switcher } = renderSwitcher();
    fireEvent.click(crumb());
    fireEvent.change(search(), { target: { value: 'api' } });
    fireEvent.keyDown(search(), { key: 'Enter' });
    expect(switcher.onPick).toHaveBeenCalledWith('p-mid', 'local');
  });

  it('a remote project is listed with its tag and picked as shared', () => {
    const { switcher } = renderSwitcher({ sharedProjects: [{ id: 's-team', name: 'team-repo', latestDate: '2026-07-01' }] });
    fireEvent.click(crumb());
    const row = screen.getByRole('option', { name: /team-repo/ });
    expect(within(row).getByText('remote')).toBeInTheDocument();
    fireEvent.click(row);
    expect(switcher.onPick).toHaveBeenCalledWith('s-team', 'shared');
  });

  it('picking the current project just closes', () => {
    const { switcher } = renderSwitcher();
    fireEvent.click(crumb());
    fireEvent.click(screen.getByRole('option', { name: /old-repo/ }));
    expect(switcher.onPick).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Escape closes and returns focus to the crumb', () => {
    renderSwitcher();
    fireEvent.click(crumb());
    fireEvent.keyDown(search(), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(crumb()).toHaveFocus();
  });

  it('an outside press closes it', () => {
    renderSwitcher();
    fireEvent.click(crumb());
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Cmd+P / Ctrl+P opens it and suppresses the print dialog', () => {
    renderSwitcher();
    const mac = /Mac|iPhone|iPad|iPod/.test(navigator.platform || '') || /Mac OS X/.test(navigator.userAgent || '');
    const event = new KeyboardEvent('keydown', { key: 'p', metaKey: mac, ctrlKey: !mac, bubbles: true, cancelable: true });
    act(() => { document.dispatchEvent(event); });
    expect(event.defaultPrevented).toBe(true);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('footer buttons open Repositories and the add flow', () => {
    const { switcher } = renderSwitcher();
    fireEvent.click(crumb());
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'all repositories' }));
    expect(switcher.onAllRepositories).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(crumb());
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /add project/ }));
    expect(switcher.onAddProject).toHaveBeenCalledTimes(1);
  });

  it('with zero projects the crumb keeps navigating to Repositories and Cmd+P is left alone', () => {
    const { onSelectProject } = renderSwitcher({ projects: [] });
    fireEvent.click(screen.getByRole('button', { name: 'old-repo' }));
    expect(onSelectProject).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
    const event = new KeyboardEvent('keydown', { key: 'p', metaKey: true, ctrlKey: true, bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});
