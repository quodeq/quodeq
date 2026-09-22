import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { CardFooter } from './CardFooter.jsx';

describe('CardFooter', () => {
  it('publish button does not call onPublish while a publish is already running', () => {
    const onPublish = vi.fn();
    render(
      <CardFooter
        name="proj-a"
        confirming={null}
        setConfirming={() => {}}
        action="publish"
        publishActions={{ publishState: 'running', publishingProject: 'proj-b', onPublish }}
      />,
    );
    fireEvent.click(screen.getByText(/publish/i));
    expect(onPublish).not.toHaveBeenCalled();
  });

  it('publish button calls onPublish with the project name when idle', () => {
    const onPublish = vi.fn();
    render(
      <CardFooter
        name="proj-a"
        confirming={null}
        setConfirming={() => {}}
        action="publish"
        publishActions={{ publishState: 'idle', publishingProject: null, onPublish }}
      />,
    );
    fireEvent.click(screen.getByText(/publish/i));
    expect(onPublish).toHaveBeenCalledWith('proj-a');
  });
});
