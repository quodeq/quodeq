import { describe, it, expect } from 'vitest';
import { fileUrlFromPath, pathFromFileUrl } from './fileUrl.js';

describe('fileUrlFromPath', () => {
  it('prefixes a posix path as is', () => {
    expect(fileUrlFromPath('/Users/me/evals.git')).toBe('file:///Users/me/evals.git');
  });

  it('adds the slash before a Windows drive and forward-slashes the path', () => {
    expect(fileUrlFromPath('C:\\Users\\me\\evals.git')).toBe('file:///C:/Users/me/evals.git');
    expect(fileUrlFromPath('d:/work/evals')).toBe('file:///d:/work/evals');
  });
});

describe('pathFromFileUrl', () => {
  it('returns the posix path and drops the slash before a Windows drive', () => {
    expect(pathFromFileUrl('file:///Users/me/evals.git')).toBe('/Users/me/evals.git');
    expect(pathFromFileUrl('file:///C:/Users/me/evals.git')).toBe('C:/Users/me/evals.git');
  });

  it('is empty for anything that is not a file url', () => {
    expect(pathFromFileUrl('https://github.com/team/evaluations.git')).toBe('');
    expect(pathFromFileUrl('')).toBe('');
    expect(pathFromFileUrl(null)).toBe('');
  });
});
