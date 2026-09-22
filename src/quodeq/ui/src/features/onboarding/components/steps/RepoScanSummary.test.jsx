import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { RepoScanSummary } from './RepoScanSummary.jsx';

// #1209: the FILES tile counts what the run will score. When git leaves files
// out, the tile says how many, so a total smaller than the directory has a
// visible reason.
describe('RepoScanSummary untracked files', () => {
  it('explains the untracked files git will not score', () => {
    render(<RepoScanSummary scan={{ total_files: 2889, code_files: 2000, untracked_files: 5, languages: {}, branches: [] }} />);
    expect(screen.getByText('2889')).toBeInTheDocument();
    expect(screen.getByText('5 untracked, not scored')).toBeInTheDocument();
  });

  it('keeps the plain hint when nothing is untracked', () => {
    render(<RepoScanSummary scan={{ total_files: 10, code_files: 4, untracked_files: 0, languages: {}, branches: [] }} />);
    expect(screen.getByText('all files in repo')).toBeInTheDocument();
    expect(screen.queryByText(/untracked/)).toBeNull();
  });
});
