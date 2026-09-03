import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useRelocateDialog } from './ProjectCardGroup.jsx';
import { ProjectPathContent } from './ProjectPathContent.jsx';

describe('useRelocateDialog', () => {
  it('does not close the relocate dialog for a blank path, and surfaces an error', () => {
    const onRelocate = vi.fn();
    const { result } = renderHook(() => useRelocateDialog(onRelocate));
    act(() => result.current.startRelocate('proj', ''));
    act(() => result.current.submitRelocate('proj'));
    expect(result.current.relocating).toBe('proj'); // dialog stays open
    expect(result.current.relocateError).toBeTruthy();
    expect(onRelocate).not.toHaveBeenCalled();
  });

  it('does not close the dialog for a whitespace-only path', () => {
    const onRelocate = vi.fn();
    const { result } = renderHook(() => useRelocateDialog(onRelocate));
    act(() => result.current.startRelocate('proj', ''));
    act(() => result.current.setRelocatePath('   '));
    act(() => result.current.submitRelocate('proj'));
    expect(result.current.relocating).toBe('proj');
    expect(result.current.relocateError).toBeTruthy();
    expect(onRelocate).not.toHaveBeenCalled();
  });

  it('clears any prior error and submits normally for a non-blank path', () => {
    const onRelocate = vi.fn();
    const { result } = renderHook(() => useRelocateDialog(onRelocate));
    act(() => result.current.startRelocate('proj', ''));
    act(() => result.current.submitRelocate('proj')); // sets relocateError
    act(() => result.current.setRelocatePath('/new/path'));
    act(() => result.current.submitRelocate('proj'));
    expect(onRelocate).toHaveBeenCalledWith('proj', '/new/path');
    expect(result.current.relocating).toBeNull();
  });

  it('resets relocateError when a new relocate is started', () => {
    const onRelocate = vi.fn();
    const { result } = renderHook(() => useRelocateDialog(onRelocate));
    act(() => result.current.startRelocate('proj', ''));
    act(() => result.current.submitRelocate('proj'));
    expect(result.current.relocateError).toBeTruthy();
    act(() => result.current.startRelocate('proj', '/existing'));
    expect(result.current.relocateError).toBeNull();
  });
});

describe('ProjectPathContent relocate error rendering', () => {
  function Wrapper() {
    const relocateActions = useRelocateDialog(vi.fn());
    return (
      <>
        <button type="button" onClick={() => relocateActions.startRelocate('proj', '')}>start</button>
        <ProjectPathContent id="proj" p={{ path: null, location: 'local', pathExists: false }} relocateActions={relocateActions} />
      </>
    );
  }

  it('shows an error message in the dialog when a blank path is submitted', () => {
    render(<Wrapper />);
    fireEvent.click(screen.getByText('start'));
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    expect(screen.getByText(/path/i)).toBeInTheDocument();
    // The dialog must still be open (input still present) after rejection.
    expect(screen.getByPlaceholderText('/new/path/to/repo')).toBeInTheDocument();
  });
});
