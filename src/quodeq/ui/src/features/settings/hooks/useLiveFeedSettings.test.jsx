import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import useLiveFeedSettings, { NEW_FINDINGS_ONLY_KEY } from './useLiveFeedSettings.js';

function Probe() {
  const { newOnly, setNewOnly } = useLiveFeedSettings();
  return (
    <button onClick={() => setNewOnly(!newOnly)}>
      {newOnly ? 'new-only' : 'all'}
    </button>
  );
}

describe('useLiveFeedSettings', () => {
  beforeEach(() => { localStorage.clear(); });

  it('defaults to new-only', () => {
    render(<Probe />);
    expect(screen.getByRole('button')).toHaveTextContent('new-only');
  });

  it('treats only the literal "false" as opt-out', () => {
    localStorage.setItem(NEW_FINDINGS_ONLY_KEY, 'false');
    render(<Probe />);
    expect(screen.getByRole('button')).toHaveTextContent('all');
  });

  it('persists the choice', () => {
    render(<Probe />);
    act(() => { screen.getByRole('button').click(); });
    expect(localStorage.getItem(NEW_FINDINGS_ONLY_KEY)).toBe('false');
    expect(screen.getByRole('button')).toHaveTextContent('all');
  });

  it('syncs a second consumer in the same tab', () => {
    // A storage event does not fire in the tab that wrote the value, so the
    // hook dispatches its own. Without it the Settings page and the
    // evaluation screen disagree until a reload.
    render(<><Probe /><Probe /></>);
    const [first, second] = screen.getAllByRole('button');
    act(() => { first.click(); });
    expect(second).toHaveTextContent('all');
  });
});
