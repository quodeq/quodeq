import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useFolderNavigation } from './useFolderNavigation.js';

function wrapper(api) {
  return function Wrapper({ children }) {
    return <ApiProvider value={api}>{children}</ApiProvider>;
  };
}

describe('useFolderNavigation', () => {
  it('navigates on mount to rootPath and loads directories', async () => {
    const browseDirectory = vi.fn().mockResolvedValue({
      current: '/repo', parent: '/', directories: [{ path: '/repo/a', name: 'a', isGitRepo: false }], files: [],
    });
    const { result } = renderHook(() => useFolderNavigation({ rootPath: '/repo', showFiles: false }), {
      wrapper: wrapper({ browseDirectory }),
    });

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(browseDirectory).toHaveBeenCalledWith('/repo', { files: false });
    expect(result.current.data.current).toBe('/repo');
    expect(result.current.pathInput).toBe('/repo');
    expect(result.current.selectedFolder).toBe('/repo');
    expect(result.current.navError).toBeNull();
  });

  it('navigate success: updates data/pathInput/selectedFolder from the result', async () => {
    const browseDirectory = vi.fn()
      .mockResolvedValueOnce({ current: '', parent: null, directories: [], files: [] })
      .mockResolvedValueOnce({ current: '/repo/sub', parent: '/repo', directories: [], files: [] });
    const { result } = renderHook(() => useFolderNavigation({ rootPath: null, showFiles: false }), {
      wrapper: wrapper({ browseDirectory }),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => { await result.current.navigate('/repo/sub'); });

    expect(result.current.data.current).toBe('/repo/sub');
    expect(result.current.pathInput).toBe('/repo/sub');
    expect(result.current.selectedFolder).toBe('/repo/sub');
  });

  it('navigate error: sets navError and clears loading, keeps prior data', async () => {
    const browseDirectory = vi.fn()
      .mockResolvedValueOnce({ current: '/repo', parent: '/', directories: [], files: [] })
      .mockRejectedValueOnce(Object.assign(new Error('nope'), { code: 'NOT_FOUND' }));
    const { result } = renderHook(() => useFolderNavigation({ rootPath: '/repo', showFiles: false }), {
      wrapper: wrapper({ browseDirectory }),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => { await result.current.navigate('/repo/missing'); });

    expect(result.current.loading).toBe(false);
    expect(result.current.navError).toEqual(expect.any(String));
    // Prior data is untouched by a failed navigation.
    expect(result.current.data.current).toBe('/repo');
  });

  it('navigate above rootPath is blocked: resets pathInput to rootPath without calling the API', async () => {
    const browseDirectory = vi.fn().mockResolvedValue({ current: '/repo', parent: '/', directories: [], files: [] });
    const { result } = renderHook(() => useFolderNavigation({ rootPath: '/repo', showFiles: false }), {
      wrapper: wrapper({ browseDirectory }),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    browseDirectory.mockClear();

    act(() => { result.current.navigate('/'); });

    expect(browseDirectory).not.toHaveBeenCalled();
    expect(result.current.pathInput).toBe('/repo');
  });

  it('setSelectedFolder and setPathInput update state directly', async () => {
    const browseDirectory = vi.fn().mockResolvedValue({ current: '/repo', parent: '/', directories: [], files: [] });
    const { result } = renderHook(() => useFolderNavigation({ rootPath: '/repo', showFiles: false }), {
      wrapper: wrapper({ browseDirectory }),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => { result.current.setSelectedFolder('/repo/x'); });
    expect(result.current.selectedFolder).toBe('/repo/x');

    act(() => { result.current.setPathInput('/typed'); });
    expect(result.current.pathInput).toBe('/typed');
  });
});
