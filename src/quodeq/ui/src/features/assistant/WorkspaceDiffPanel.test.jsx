import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../api/assistant.js', () => ({
  fetchAssistantWorkspaceDiff: vi.fn().mockResolvedValue({
    diff: 'diff --git a/x b/x\n@@ -1 +1 @@\n-a\n+b\n', stats: [{ file: 'x', added: 1, deleted: 1 }],
  }),
  applyAssistantWorkspace: vi.fn().mockResolvedValue({ applied: true, stats: [] }),
  createAssistantWorkspacePr: vi.fn().mockResolvedValue({ prUrl: 'http://pr/1', branch: 'b', pushed: true, message: 'PR created' }),
  discardAssistantWorkspace: vi.fn().mockResolvedValue({ discarded: true }),
}));
vi.mock('../../utils/confirmDialog.js', () => ({ confirmDialog: vi.fn() }));

import { applyAssistantWorkspace, discardAssistantWorkspace } from '../../api/assistant.js';
import { confirmDialog } from '../../utils/confirmDialog.js';
import { ApiProvider } from '../../api/ApiContext.jsx';
import { WorkspaceDiffPanel, classifyDiffLine, DIFF_LINE_RENDER_CAP } from './WorkspaceDiffPanel.jsx';

function makeFakeApi(overrides = {}) {
  return {
    fetchAssistantWorkspaceDiff: vi.fn().mockResolvedValue({
      diff: 'diff --git a/x b/x\n@@ -1 +1 @@\n-a\n+b\n', truncated: false, stats: [],
    }),
    applyAssistantWorkspace: vi.fn().mockResolvedValue({ applied: true, stats: [] }),
    createAssistantWorkspacePr: vi.fn().mockResolvedValue({
      prUrl: 'http://pr/1', branch: 'b', pushed: true, message: 'PR created',
    }),
    discardAssistantWorkspace: vi.fn().mockResolvedValue({ discarded: true }),
    ...overrides,
  };
}

describe('classifyDiffLine', () => {
  it('classifies diff lines', () => {
    expect(classifyDiffLine('+new')).toBe('wsdiff-add');
    expect(classifyDiffLine('-old')).toBe('wsdiff-del');
    expect(classifyDiffLine('+++ b/x')).toBe('wsdiff-file');
    expect(classifyDiffLine('@@ -1 +1 @@')).toBe('wsdiff-hunk');
    expect(classifyDiffLine(' ctx')).toBe('wsdiff-ctx');
  });
});

describe('WorkspaceDiffPanel', () => {
  it('loads the diff and applies on click', async () => {
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('+b')).toBeTruthy());
    fireEvent.click(screen.getByText('Apply to repo'));
    await waitFor(() => expect(applyAssistantWorkspace).toHaveBeenCalledWith('s1'));
    await waitFor(() => expect(screen.getByText(/applied to your working tree/i)).toBeTruthy());
  });

  it('warns when the diff is truncated', async () => {
    const api = await import('../../api/assistant.js');
    api.fetchAssistantWorkspaceDiff.mockResolvedValueOnce({ diff: 'diff --git a/x b/x\n+big\n', truncated: true, stats: [] });
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByText(/truncated at 2 MB/i)).toBeTruthy();
  });

  it('keeps the buttons after a fail-soft PR (no prUrl)', async () => {
    const api = await import('../../api/assistant.js');
    api.createAssistantWorkspacePr.mockResolvedValueOnce({ prUrl: null, branch: 'b', pushed: false, message: 'Push failed. Branch kept.' });
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Apply to repo')).toBeTruthy());
    fireEvent.click(screen.getByText('Create PR...'));
    fireEvent.click(screen.getByText('Create PR'));
    await waitFor(() => expect(screen.getByText(/Push failed/i)).toBeTruthy());
    // still reviewable: Apply/Discard remain
    expect(screen.getByText('Apply to repo')).toBeTruthy();
    expect(screen.getByText('Discard')).toBeTruthy();
  });

  it('shows a terminal message when the branch pushed but no PR was created', async () => {
    const api = await import('../../api/assistant.js');
    api.createAssistantWorkspacePr.mockResolvedValueOnce({ prUrl: null, branch: 'b', pushed: true, message: 'Branch pushed. Open the PR from your git host.' });
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Apply to repo')).toBeTruthy());
    fireEvent.click(screen.getByText('Create PR...'));
    fireEvent.click(screen.getByText('Create PR'));
    await waitFor(() => expect(screen.getByText(/Branch pushed/i)).toBeTruthy());
    // terminal: Apply button is gone
    expect(screen.queryByText('Apply to repo')).toBeNull();
  });

  it('shows an empty-state message when there are no changes', async () => {
    const api = await import('../../api/assistant.js');
    api.fetchAssistantWorkspaceDiff.mockResolvedValueOnce({ diff: '', truncated: false, stats: [] });
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/No changes in this worktree/i)).toBeTruthy());
  });

  it('does not discard when the confirm dialog is cancelled', async () => {
    confirmDialog.mockResolvedValueOnce(false);
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Discard')).toBeTruthy());
    fireEvent.click(screen.getByText('Discard'));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'danger' }),
    ));
    expect(discardAssistantWorkspace).not.toHaveBeenCalled();
  });

  it('discards when the confirm dialog is accepted', async () => {
    confirmDialog.mockResolvedValueOnce(true);
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Discard')).toBeTruthy());
    fireEvent.click(screen.getByText('Discard'));
    await waitFor(() => expect(discardAssistantWorkspace).toHaveBeenCalledWith('s1'));
  });
});

// Discriminating regression test for "Panel imports concrete API functions
// directly, bypassing the hook's DI": these tests supply the API functions
// only via a custom ApiProvider value (never via the module-level vi.mock
// above), so they can only pass if the Panel's Apply/Create PR/Discard
// buttons actually route through useWorkspaceDiff's useApi() resolution.
// Pre-fix, the Panel called the statically-imported functions from
// '../../api/assistant.js' and these fake ApiProvider functions would never
// be invoked.
describe('WorkspaceDiffPanel API injection', () => {
  it('routes "Apply to repo" through the injected ApiProvider', async () => {
    const fakeApi = makeFakeApi();
    render(
      <ApiProvider value={fakeApi}>
        <WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />
      </ApiProvider>,
    );
    await waitFor(() => expect(screen.getByText('+b')).toBeTruthy());
    fireEvent.click(screen.getByText('Apply to repo'));
    await waitFor(() => expect(fakeApi.applyAssistantWorkspace).toHaveBeenCalledWith('s1'));
    await waitFor(() => expect(screen.getByText(/applied to your working tree/i)).toBeTruthy());
  });

  it('routes "Create PR" through the injected ApiProvider', async () => {
    const fakeApi = makeFakeApi();
    render(
      <ApiProvider value={fakeApi}>
        <WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />
      </ApiProvider>,
    );
    await waitFor(() => expect(screen.getByText('Apply to repo')).toBeTruthy());
    fireEvent.click(screen.getByText('Create PR...'));
    fireEvent.click(screen.getByText('Create PR'));
    await waitFor(() => expect(fakeApi.createAssistantWorkspacePr).toHaveBeenCalledWith(
      's1', expect.objectContaining({ title: expect.any(String), body: '' }),
    ));
  });

  it('routes "Discard" (after confirm) through the injected ApiProvider', async () => {
    confirmDialog.mockResolvedValueOnce(true);
    const fakeApi = makeFakeApi();
    render(
      <ApiProvider value={fakeApi}>
        <WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />
      </ApiProvider>,
    );
    await waitFor(() => expect(screen.getByText('Discard')).toBeTruthy());
    fireEvent.click(screen.getByText('Discard'));
    await waitFor(() => expect(fakeApi.discardAssistantWorkspace).toHaveBeenCalledWith('s1'));
  });
});

describe('WorkspaceDiffPanel render cap', () => {
  const bigDiff = (n, tag) => Array.from({ length: n }, (_, i) => `+${tag}${i}`).join('\n');
  const shownSpans = (container) => container.querySelectorAll('.workspace-diff-body span').length;

  it('mounts only the first DIFF_LINE_RENDER_CAP lines and a note', async () => {
    const api = await import('../../api/assistant.js');
    api.fetchAssistantWorkspaceDiff.mockResolvedValueOnce({ diff: bigDiff(2500, 'a'), truncated: false, stats: [] });
    const { container } = render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Showing 2000 of 2500 lines.')).toBeTruthy());
    expect(shownSpans(container)).toBe(DIFF_LINE_RENDER_CAP);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('Show more mounts the rest and hides the note and the button', async () => {
    const api = await import('../../api/assistant.js');
    api.fetchAssistantWorkspaceDiff.mockResolvedValueOnce({ diff: bigDiff(2500, 'a'), truncated: false, stats: [] });
    const { container } = render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Show more')).toBeTruthy());
    fireEvent.click(screen.getByText('Show more'));
    expect(shownSpans(container)).toBe(2500);
    expect(screen.queryByText('Show more')).toBeNull();
    expect(screen.queryByText(/Showing \d+ of/)).toBeNull();
  });

  it('a new diff after Refresh starts from the cap again', async () => {
    const api = await import('../../api/assistant.js');
    api.fetchAssistantWorkspaceDiff
      .mockResolvedValueOnce({ diff: bigDiff(2500, 'a'), truncated: false, stats: [] })
      .mockResolvedValueOnce({ diff: bigDiff(3000, 'b'), truncated: false, stats: [] });
    const { container } = render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Show more')).toBeTruthy());
    fireEvent.click(screen.getByText('Show more'));
    fireEvent.click(screen.getByText('Refresh'));
    await waitFor(() => expect(screen.getByText('Showing 2000 of 3000 lines.')).toBeTruthy());
    expect(shownSpans(container)).toBe(DIFF_LINE_RENDER_CAP);
  });

  it('a small diff shows no cap note and no button', async () => {
    render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('+b')).toBeTruthy());
    expect(screen.queryByText('Show more')).toBeNull();
  });

  it('does not count the trailing empty line after a final newline', async () => {
    const api = await import('../../api/assistant.js');
    // Exactly DIFF_LINE_RENDER_CAP real lines, ending with a newline (as a
    // real diff always does). Before the fix this counted as 2001 lines and
    // wrongly showed a cap note and a Show more button.
    const diff = `${bigDiff(DIFF_LINE_RENDER_CAP, 'a')}\n`;
    api.fetchAssistantWorkspaceDiff.mockResolvedValueOnce({ diff, truncated: false, stats: [] });
    const { container } = render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('+a1999')).toBeTruthy());
    expect(shownSpans(container)).toBe(DIFF_LINE_RENDER_CAP);
    expect(screen.queryByText('Show more')).toBeNull();
    expect(screen.queryByText(/Showing \d+ of/)).toBeNull();
  });

  it('keeps the cap note in a pre-mounted live region and focuses the diff after the last Show more', async () => {
    const api = await import('../../api/assistant.js');
    api.fetchAssistantWorkspaceDiff.mockResolvedValueOnce({ diff: bigDiff(2500, 'a'), truncated: false, stats: [] });
    const { container } = render(<WorkspaceDiffPanel sessionId="s1" onChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Show more')).toBeTruthy());

    const note = container.querySelector('.workspace-diff-warning[aria-live="polite"]');
    expect(note).toBeTruthy();
    expect(note.textContent).toBe('Showing 2000 of 2500 lines.');

    fireEvent.click(screen.getByText('Show more'));

    // Same node, still mounted, now empty; the button is gone.
    const noteAfter = container.querySelector('.workspace-diff-warning[aria-live="polite"]');
    expect(noteAfter).toBe(note);
    expect(noteAfter.textContent).toBe('');
    expect(screen.queryByText('Show more')).toBeNull();

    // Focus moved to the diff instead of falling to <body>.
    const pre = container.querySelector('pre.workspace-diff-body');
    expect(document.activeElement).toBe(pre);
  });
});
